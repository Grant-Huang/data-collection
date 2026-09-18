import random
import uuid
from datetime import datetime, timedelta
from typing import Dict, List
import pandas as pd
import networkx as nx
from .catalog import MICROFLOWS, SCENARIOS, SCENARIO_EDGES, SCENARIO_CONTROL_GROUPS, TOOL_VARIANTS
from .graph_utils import dump_ids, parse_ids

IRRELEVANT_CAPABILITIES = [
    "ReadUnrelatedDashboard", "SendStatusMessage", "CheckShiftCalendar",
    "OpenReferenceDocument", "QueryNonCriticalMetric"
]

def _tool_for(capability: str, rng: random.Random, heterogeneity: int) -> str:
    variants = TOOL_VARIANTS.get(capability)
    if not variants:
        return capability
    k = max(1, min(heterogeneity, len(variants)))
    return rng.choice(variants[:k])

def _object_type(capability: str) -> str:
    c = capability.lower()
    if "machine" in c or "alarm" in c or "capacity" in c or "process" in c:
        return "Machine"
    if "quality" in c or "inspection" in c or "wip" in c:
        return "QualityIssue"
    if "order" in c or "schedule" in c or "delivery" in c or "commitment" in c:
        return "ProductionOrder"
    if "maintenance" in c:
        return "MaintenanceRequest"
    return "OperationalCase"

def _control_meta(mw, capability):
    meta = {"branch_group_id":"","branch_type":"","join_policy":"","control_role":""}
    for cg in mw.control_groups:
        if capability == cg.fork_from and capability:
            meta.update(branch_group_id=cg.group_id, branch_type=cg.branch_type, control_role="fork")
        if capability in cg.branch_members:
            meta.update(branch_group_id=cg.group_id, branch_type=cg.branch_type, control_role="branch")
        if capability == cg.join_to and capability:
            meta.update(branch_group_id=cg.group_id, branch_type=cg.branch_type,
                        join_policy=cg.join_policy, control_role="join")
    return meta

def _record(case_id, scenario, episode_id, mw_id, t, capability, intent,
            action_type, actor_type, actor_role, tool_name, status="success",
            retry_count=0, variation_type="normative", predecessor_ids=None,
            control_meta=None):
    control_meta = control_meta or {}
    event_id = str(uuid.uuid4())
    return {
        "event_id": event_id,
        "case_id": case_id,
        "scenario": scenario,
        "episode_id_gt": episode_id,
        "microflow_gt": mw_id,
        "timestamp": t.isoformat(),
        "actor_type": actor_type,
        "actor_role": actor_role,
        "intent": intent,
        "action_type": action_type,
        "capability": capability,
        "tool_name": tool_name,
        "object_type": _object_type(capability),
        "status": status,
        "retry_count": retry_count,
        "variation_type": variation_type,
        "predecessor_event_ids_gt": dump_ids(predecessor_ids or []),
        "predecessor_event_ids": dump_ids(predecessor_ids or []),
        "branch_group_id": control_meta.get("branch_group_id", ""),
        "branch_type": control_meta.get("branch_type", ""),
        "join_policy": control_meta.get("join_policy", ""),
        "control_role": control_meta.get("control_role", ""),
        "dependency_source": "synthetic_observed",
    }

def _variant_graph(mw, rng, business_variation_rate):
    nodes = {s.capability: s for s in mw.steps}
    g = nx.DiGraph(); g.add_nodes_from(nodes); g.add_edges_from(mw.graph_edges())

    # Legitimate omission: remove an interior node and bridge its predecessors/successors.
    candidates = [n for n in g.nodes if g.in_degree(n)>0 and g.out_degree(n)>0]
    if candidates and rng.random() < business_variation_rate:
        n = rng.choice(candidates)
        preds, succs = list(g.predecessors(n)), list(g.successors(n))
        g.remove_node(n); nodes.pop(n, None)
        for a in preds:
            for b in succs:
                if a != b: g.add_edge(a,b)

    # OR-like branch variation: some evidence branches are legitimately optional.
    for cg in mw.control_groups:
        if cg.branch_type == "or" and rng.random() < business_variation_rate:
            present = [x for x in cg.branch_members if x in g]
            if len(present) > 2:
                n = rng.choice(present)
                preds, succs = list(g.predecessors(n)), list(g.successors(n))
                g.remove_node(n); nodes.pop(n, None)
                for a in preds:
                    for b in succs:
                        if a != b: g.add_edge(a,b)
    return nodes, g

def _episode_order(scenario):
    members = list(SCENARIOS[scenario])
    g = nx.DiGraph(); g.add_nodes_from(members); g.add_edges_from(SCENARIO_EDGES.get(scenario, []))
    return g, list(nx.topological_sort(g))

def generate_dataset(
    n_cases: int = 500,
    business_variation_rate: float = 0.10,
    execution_deviation_rate: float = 0.08,
    logging_error_rate: float = 0.03,
    tool_heterogeneity: int = 3,
    human_variant_rate: float = 0.15,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate AgentNexus-like collaborative work DAGs with hidden ground truth.

    Temporal order and work dependency are represented separately. Parallel branches may
    interleave in time, while ``predecessor_event_ids`` preserves causal/work dependency.
    """
    rng = random.Random(seed)
    records: List[Dict] = []
    base_time = datetime(2026, 1, 1, 8, 0, 0)

    for case_idx in range(n_cases):
        case_id = f"C{case_idx:06d}"
        scenario = rng.choice(list(SCENARIOS))
        sg, episode_order = _episode_order(scenario)
        case_start = base_time + timedelta(minutes=case_idx * 4)
        episode_terminal_ids = {}
        episode_end_time = {}

        for epi_idx, mw_id in enumerate(episode_order):
            mw = MICROFLOWS[mw_id]
            episode_id = f"{case_id}_{mw_id}"
            pred_eps = list(sg.predecessors(mw_id))
            cross_pred_ids = [eid for p in pred_eps for eid in episode_terminal_ids.get(p, [])]
            if pred_eps:
                start_t = max(episode_end_time[p] for p in pred_eps) + timedelta(seconds=rng.randint(2,18))
            else:
                start_t = case_start + timedelta(seconds=rng.randint(0,8))

            steps, g = _variant_graph(mw, rng, business_variation_rate)
            cap_to_success_event = {}
            cap_end_time = {}
            topo_generations = list(nx.topological_generations(g)) if len(g) else []

            for level, generation in enumerate(topo_generations):
                level_base = start_t + timedelta(seconds=level * rng.randint(25,55))
                for pos, cap in enumerate(sorted(generation)):
                    step = steps[cap]
                    actor_type, actor_role = step.actor_type, step.actor_role
                    if actor_type == "agent" and rng.random() < human_variant_rate and step.action_type not in ("trigger","outcome"):
                        actor_type, actor_role = "human", "specialist"

                    pred_caps = list(g.predecessors(cap))
                    predecessor_ids = [cap_to_success_event[p] for p in pred_caps if p in cap_to_success_event]
                    if not pred_caps:
                        predecessor_ids += cross_pred_ids
                    t = level_base + timedelta(seconds=rng.randint(0,15) + pos*2)

                    # Supporting activity becomes an observable detour but does not change GT microflow identity.
                    if rng.random() < business_variation_rate / 2:
                        support_cap = rng.choice(IRRELEVANT_CAPABILITIES)
                        support = _record(
                            case_id, scenario, episode_id, mw_id, t,
                            support_cap, "supporting_activity", "support",
                            "agent", rng.choice(["production","planning","quality","maintenance"]),
                            support_cap, variation_type="business_variation",
                            predecessor_ids=predecessor_ids,
                        )
                        records.append(support)
                        predecessor_ids = [support["event_id"]]
                        t += timedelta(seconds=rng.randint(3,10))

                    retry_count = 0
                    if rng.random() < execution_deviation_rate:
                        fail = _record(
                            case_id, scenario, episode_id, mw_id, t,
                            cap, step.intent, step.action_type, actor_type, actor_role,
                            _tool_for(cap, rng, tool_heterogeneity), status="failed",
                            variation_type="execution_deviation", predecessor_ids=predecessor_ids,
                            control_meta=_control_meta(mw, cap),
                        )
                        records.append(fail)
                        predecessor_ids = [fail["event_id"]]
                        retry_count = 1
                        t += timedelta(seconds=rng.randint(4,12))

                    r = _record(
                        case_id, scenario, episode_id, mw_id, t,
                        cap, step.intent, step.action_type, actor_type, actor_role,
                        _tool_for(cap, rng, tool_heterogeneity), retry_count=retry_count,
                        predecessor_ids=predecessor_ids, control_meta=_control_meta(mw, cap),
                    )
                    records.append(r)
                    cap_to_success_event[cap] = r["event_id"]
                    cap_end_time[cap] = t

            terminals = [n for n in g.nodes if g.out_degree(n)==0]
            episode_terminal_ids[mw_id] = [cap_to_success_event[x] for x in terminals if x in cap_to_success_event]
            episode_end_time[mw_id] = max([cap_end_time[x] for x in terminals if x in cap_end_time] or [start_t])

        # Add episode-level control metadata to roots/joins when applicable.
        case_rows = [r for r in records if r["case_id"] == case_id]
        for cg in SCENARIO_CONTROL_GROUPS.get(scenario, []):
            group_id = f"{case_id}-{cg.group_id}"
            for r in case_rows:
                if r["microflow_gt"] in cg.branch_members and not parse_ids(r["predecessor_event_ids_gt"]):
                    r["branch_group_id"] = group_id; r["branch_type"] = cg.branch_type; r["control_role"] = "branch"
                if r["microflow_gt"] == cg.join_to:
                    # mark only roots of join episode
                    preds = parse_ids(r["predecessor_event_ids_gt"])
                    pred_eps = {next((x["microflow_gt"] for x in case_rows if x["event_id"]==pid),"") for pid in preds}
                    if len(pred_eps) > 1:
                        r["branch_group_id"] = group_id; r["branch_type"] = cg.branch_type; r["join_policy"] = cg.join_policy; r["control_role"] = "join"

    df = pd.DataFrame(records).sort_values(["case_id","timestamp","event_id"]).reset_index(drop=True)

    # Observation-layer imperfections. Ground-truth IDs remain hidden columns for evaluation;
    # observed dependency links are filtered to retained events.
    if logging_error_rate > 0 and not df.empty:
        observed = []
        for _, row in df.iterrows():
            if rng.random() < logging_error_rate / 2:
                continue
            observed.append(row.to_dict())
            if rng.random() < logging_error_rate / 4:
                dup = row.to_dict(); dup["event_id"] = str(uuid.uuid4())
                dup["variation_type"] = "logging_error_duplicate"
                observed.append(dup)
        df = pd.DataFrame(observed)
        if not df.empty:
            valid = set(df["event_id"].astype(str))
            df["predecessor_event_ids"] = df["predecessor_event_ids"].apply(
                lambda x: dump_ids([p for p in parse_ids(x) if p in valid]))
            ts = pd.to_datetime(df["timestamp"])
            jitter = [rng.randint(-20,20) if rng.random() < logging_error_rate/3 else 0 for _ in range(len(df))]
            df["timestamp"] = (ts + pd.to_timedelta(jitter, unit="s")).dt.strftime("%Y-%m-%dT%H:%M:%S")
            df = df.sort_values(["case_id","timestamp","event_id"]).reset_index(drop=True)
    return df
