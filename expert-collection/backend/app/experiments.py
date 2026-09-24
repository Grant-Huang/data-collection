"""Experiment Center execution engine -- PRD 14, honestly scoped per IMPLEMENTATION_PLAN.md
section 7: this product's graphs are produced directly by structured conversation, not
extracted from raw text against a separate Gold standard, so most of PRD 14.3's metrics
(which assume a Gold annotation to compare against) have no real ground truth to compute
against here. `consensus_dfg` is the hand-rolled baseline: a train/test split where the
"prediction" is a consensus structure mined (real Directly-Follows Graph mining, hence the
name) from the train split, evaluated against the held-out test split.

`pm4py_inductive`/`pm4py_heuristics` (IMPLEMENTATION_PLAN.md §14) run the same train/test
comparison but through the real pm4py library's Inductive Miner / Heuristics Miner instead of
the hand-rolled medoid-sequence baseline -- see `run_pm4py_method` for how a DAG becomes an
event log pm4py can mine, and what its native fitness/precision metrics map onto.

`llm_extractor` (a batch text-to-graph extraction pipeline, unrelated to guide_service's
real-time conversational one) is still a real, selectable option in the create-experiment form
(matching the PRD's field design) but has no execution engine wired up this round -- it needs
its own input/output protocol design (IMPLEMENTATION_PLAN.md §14), not just a metrics swap, so
running it fails honestly rather than faking numbers.
"""
from __future__ import annotations

import random
from typing import Any

NODE_TYPE_LABEL = {
    "start": "起点", "end": "终点", "activity": "活动", "wait": "等待",
    "decision": "判断", "parallel_split": "并行拆分", "parallel_join": "并行汇合",
    "merge": "汇合", "approval": "审批", "handoff": "交接",
}

IMPLEMENTED_METHODS = {"consensus_dfg", "pm4py_inductive", "pm4py_heuristics"}


def split_train_test(workflow_ids: list[str], seed: int, train_ratio: float) -> tuple[list[str], list[str]]:
    ids = list(workflow_ids)
    random.Random(seed).shuffle(ids)
    cut = max(1, round(len(ids) * train_ratio))
    return ids[:cut], ids[cut:] or ids[cut - 1:]  # guarantee a non-empty test split


def _main_path_types(graph: dict) -> list[str]:
    """Simple representative type sequence: from start, repeatedly take the first outgoing
    edge until a dead end. Deliberately simple -- consensus_dfg is the simple rule-based
    baseline (PRD 14.1), not meant to capture every branch.
    """
    node_by_id = {n["node_id"]: n for n in graph.get("nodes", [])}
    starts = [n for n in graph.get("nodes", []) if n["node_type"] == "start"]
    if not starts:
        return []
    edges_by_from: dict[str, list[dict]] = {}
    for e in graph.get("edges", []):
        edges_by_from.setdefault(e["from"], []).append(e)
    seq: list[str] = []
    visited: set[str] = set()
    cur: str | None = starts[0]["node_id"]
    while cur and cur not in visited:
        visited.add(cur)
        node = node_by_id.get(cur)
        if not node:
            break
        seq.append(node["node_type"])
        outs = edges_by_from.get(cur, [])
        cur = outs[0]["to"] if outs else None
    return seq


def _bigrams(seq: list[str]) -> set[tuple[str, str]]:
    return set(zip(seq, seq[1:]))


def _prf(pred: set, gold: set) -> tuple[float, float, float]:
    if not pred and not gold:
        return 1.0, 1.0, 1.0
    if not pred or not gold:
        return 0.0, 0.0, 0.0
    inter = pred & gold
    precision = len(inter) / len(pred)
    recall = len(inter) / len(gold)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def _structural_features(graph: dict) -> dict[str, bool]:
    types = {n["node_type"] for n in graph.get("nodes", [])}
    return {
        "has_decision": "decision" in types,
        "has_parallel": "parallel_split" in types,
        "has_retry": any(n.get("retry_semantics", {}) and n["retry_semantics"].get("enabled") for n in graph.get("nodes", [])),
        "is_linear": not ({"decision", "parallel_split"} & types),
    }


def _pick_medoid_sequence(seqs: list[list[str]]) -> list[str]:
    """The "consensus" is the most typical *actual* train example -- the one whose bigram
    overlap with all the others is highest -- rather than a synthesized sequence. This keeps
    every element of the mined baseline traceable back to a real collected workflow.
    """
    if not seqs:
        return []
    if len(seqs) == 1:
        return seqs[0]
    best_seq, best_score = seqs[0], -1.0
    for s in seqs:
        s_bigrams = _bigrams(s)
        score = sum(_prf(s_bigrams, _bigrams(o))[2] for o in seqs if o is not s)
        if score > best_score:
            best_score, best_seq = score, s
    return best_seq


def _sequence_to_graph(seq: list[str]) -> dict:
    nodes = []
    for i, t in enumerate(seq):
        nodes.append({
            "node_id": f"n{i}", "node_type": t, "label": NODE_TYPE_LABEL.get(t, t),
            "actor_roles": [], "decision_question": None, "confidence": 1.0,
            "expert_confirmed": False, "source_turn_ids": [], "retry_semantics": None,
            "manual_position": None,
        })
    edges = [
        {"edge_id": f"e{i}", "from": f"n{i}", "to": f"n{i+1}", "edge_type": "normal",
         "condition": None, "confidence": 1.0, "expert_confirmed": False, "source_turn_ids": []}
        for i in range(len(seq) - 1)
    ]
    start_ids = [n["node_id"] for n in nodes if n["node_type"] == "start"]
    end_ids = [n["node_id"] for n in nodes if n["node_type"] == "end"]
    return {"graph_type": "dag", "start_node_ids": start_ids, "end_node_ids": end_ids, "nodes": nodes, "edges": edges}


def _avg(vals: list[float]) -> float:
    return round(sum(vals) / len(vals), 3) if vals else 0.0


def _majority_profile(graphs: list[dict]) -> dict[str, bool]:
    feats = [_structural_features(g) for g in graphs]
    return {k: sum(f[k] for f in feats) > len(feats) / 2 for k in feats[0]} if feats else {}


def _structural_match(graph: dict, majority_profile: dict[str, bool]) -> float:
    if not majority_profile:
        return 1.0
    feats = _structural_features(graph)
    return sum(1 for k in majority_profile if majority_profile[k] == feats.get(k)) / len(majority_profile)


def _mismatch_group(feats: dict[str, bool]) -> str:
    return "含分支" if feats["has_decision"] else "含并行" if feats["has_parallel"] else "含返工" if feats["has_retry"] else "线性"


def _group_indices_by_source(source_types: list[str]) -> dict[str, list[int]]:
    """PRD §14.1's hard rule ("Test 仍必须分别报告，禁止只给一个混合总分") needs to know which
    test index came from which dataset version's source_type -- this is that grouping, shared
    by every method's per-source metrics pass below.
    """
    groups: dict[str, list[int]] = {}
    for i, s in enumerate(source_types):
        groups.setdefault(s, []).append(i)
    return groups


def _score_against_consensus(
    consensus_types: set, consensus_bigrams: set, majority_profile: dict[str, bool],
    test_graphs: list[dict], test_names: list[str], test_source_types: list[str] | None = None,
) -> tuple[dict[str, float], list[dict]]:
    sources = test_source_types or [None] * len(test_graphs)
    node_f1s, edge_f1s = [], []
    error_cases = []
    for graph, name, source in zip(test_graphs, test_names, sources):
        test_seq = _main_path_types(graph)
        test_types = set(test_seq)
        test_bigrams = _bigrams(test_seq)
        _, _, node_f1 = _prf(consensus_types, test_types)
        _, _, edge_f1 = _prf(consensus_bigrams, test_bigrams)
        node_f1s.append(node_f1)
        edge_f1s.append(edge_f1)

        structural_match = _structural_match(graph, majority_profile)
        if node_f1 < 0.6 or edge_f1 < 0.6:
            case = {
                "workflow_name": name, "node_f1": round(node_f1, 2), "edge_f1": round(edge_f1, 2),
                "structural_match": round(structural_match, 2), "group": _mismatch_group(_structural_features(graph)),
            }
            if source is not None:
                case["source_type"] = source
            error_cases.append(case)

    metrics = {
        "node_f1": _avg(node_f1s),
        "edge_f1": _avg(edge_f1s),
        "graph_structural_f1": _avg(edge_f1s),  # bigram overlap doubles as the graph-level proxy here
        "structural_match_rate": _avg([_structural_match(g, majority_profile) for g in test_graphs]),
    }
    error_cases.sort(key=lambda c: c["node_f1"])
    return metrics, error_cases


def run_consensus_dfg(
    train_graphs: list[dict], test_graphs: list[dict], test_names: list[str],
    test_source_types: list[str] | None = None,
) -> dict[str, Any]:
    train_seqs = [s for s in (_main_path_types(g) for g in train_graphs) if s]
    consensus_seq = _pick_medoid_sequence(train_seqs)
    consensus_bigrams = _bigrams(consensus_seq)
    consensus_types = set(consensus_seq)

    majority_profile = _majority_profile(train_graphs)

    metrics, error_cases = _score_against_consensus(
        consensus_types, consensus_bigrams, majority_profile, test_graphs, test_names, test_source_types,
    )

    metrics_by_source: dict[str, dict[str, float]] = {}
    if test_source_types:
        for source, idxs in _group_indices_by_source(test_source_types).items():
            sub_metrics, _ = _score_against_consensus(
                consensus_types, consensus_bigrams, majority_profile,
                [test_graphs[i] for i in idxs], [test_names[i] for i in idxs],
            )
            metrics_by_source[source] = sub_metrics

    return {
        "metrics": metrics,
        "metrics_by_source": metrics_by_source,
        "consensus_graph": _sequence_to_graph(consensus_seq),
        "error_analysis": error_cases[:10],
    }


def _graph_to_traces(graph: dict, max_traces: int = 6) -> list[list[str]]:
    """Every real path from a start node to an end node, found by walking the DAG and
    branching once per node's outgoing edges -- this naturally covers decision branches (each
    outgoing edge becomes its own continuation) and parallel splits (both branches get walked,
    just not interleaved -- interleaving order doesn't change which direct-follows relations
    exist, which is all pm4py's discovery/fitness/precision actually look at). Capped so a
    workflow with deeply nested branching can't blow up the event log; traces beyond the cap
    are simply not generated -- the same kind of honestly-incomplete tradeoff as
    `_main_path_types`'s main-path-only sequence, just a wider slice.
    """
    node_by_id = {n["node_id"]: n for n in graph.get("nodes", [])}
    edges_by_from: dict[str, list[dict]] = {}
    for e in graph.get("edges", []):
        edges_by_from.setdefault(e["from"], []).append(e)
    starts = [n["node_id"] for n in graph.get("nodes", []) if n["node_type"] == "start"]
    traces: list[list[str]] = []

    def walk(node_id: str, path: list[str], visited: frozenset[str]) -> None:
        if len(traces) >= max_traces or node_id in visited:
            return
        node = node_by_id.get(node_id)
        if not node:
            return
        path = path + [node["node_type"]]
        visited = visited | {node_id}
        outs = edges_by_from.get(node_id, [])
        if not outs:
            traces.append(path)
            return
        for e in outs:
            if len(traces) >= max_traces:
                return
            walk(e["to"], path, visited)

    for s in starts:
        walk(s, [], frozenset())
    return traces


def _build_event_log(graphs: list[dict], names: list[str]):
    """pm4py needs an event log (one row per activity occurrence, grouped by case id), not a
    graph -- `_graph_to_traces` supplies the per-workflow paths, this just lays them out as
    rows with a synthetic timestamp (pm4py only needs relative order, not real durations,
    since nothing about wall-clock time is collected in this product).

    `_case_group` is the graph's own index in `graphs`/`names`, not `name` itself -- `name` is
    only for display (error case labels) and two different records can legitimately share one
    (e.g. two workflows both called "设备异常处理"), so it's unsafe to use for grouping rows
    back to "which original graph did this case come from" (needed below for per-source-type
    metric subsets). The index always uniquely identifies one graph.
    """
    import pandas as pd

    rows = []
    for gi, (graph, name) in enumerate(zip(graphs, names)):
        for ti, trace in enumerate(_graph_to_traces(graph)):
            case_id = f"{gi}__{ti}"
            for ei, node_type in enumerate(trace):
                rows.append({
                    "case:concept:name": case_id,
                    "concept:name": node_type,
                    "time:timestamp": pd.Timestamp("2024-01-01") + pd.Timedelta(seconds=ei),
                    "_source_name": name,
                    "_case_group": gi,
                })
    return pd.DataFrame(rows, columns=["case:concept:name", "concept:name", "time:timestamp", "_source_name", "_case_group"])


def _pm4py_fitness_precision(log, net, im, fm) -> tuple[float, float]:
    import pm4py

    if log.empty:
        return 0.0, 0.0
    fitness = pm4py.fitness_token_based_replay(log, net, im, fm)["average_trace_fitness"]
    precision = pm4py.precision_token_based_replay(log, net, im, fm)
    return fitness, precision


def _f_measure(a: float, b: float) -> float:
    return (2 * a * b / (a + b)) if (a + b) else 0.0


def _pm4py_metrics_for_indices(
    idxs: list[int], test_log, test_graphs: list[dict], net, im, fm, majority_profile: dict[str, bool],
) -> dict[str, float]:
    sub_log = test_log[test_log["_case_group"].isin(idxs)]
    fitness, precision = _pm4py_fitness_precision(sub_log, net, im, fm)
    return {
        "node_f1": round(fitness, 3),
        "edge_f1": round(_f_measure(fitness, precision), 3),
        "graph_structural_f1": round(precision, 3),
        "structural_match_rate": _avg([_structural_match(test_graphs[i], majority_profile) for i in idxs]),
    }


def run_pm4py_method(
    method: str, train_graphs: list[dict], test_graphs: list[dict], test_names: list[str],
    test_source_types: list[str] | None = None,
) -> dict[str, Any]:
    """Real process mining via the pm4py library (IMPLEMENTATION_PLAN.md §14), not a metrics
    swap on top of `run_consensus_dfg`'s hand-rolled baseline: `method` picks the actual mining
    algorithm (Inductive Miner or Heuristics Miner), and every metric below comes straight out
    of pm4py's own conformance-checking functions (token-based replay fitness/precision), not
    a bigram-overlap approximation.

    Metric mapping onto this product's existing node_f1/edge_f1/graph_structural_f1 fields (so
    the same Experiment Center UI and `compare` endpoint work unmodified across methods):
    - node_f1          <- average trace fitness (does the model reproduce most of what happens?)
    - graph_structural_f1 <- precision (does the model *avoid* allowing paths that never happened?)
    - edge_f1          <- harmonic mean of the two (a real F-measure of fitness & precision,
                           standard pm4py evaluation practice, not this product's invented metric)
    - structural_match_rate <- unchanged from run_consensus_dfg: still the majority-profile
                           comparison (has_decision/has_parallel/has_retry/is_linear), since
                           that check is about the *raw graphs*, not the mined model

    `test_source_types` (PRD §14.1's "Combined Train allowed, Test must be reported separately
    per source" rule): when given, `metrics_by_source` in the return value has one entry per
    distinct source_type among the test set, computed by filtering the same discovered model's
    conformance check down to just that source's test cases -- not a second model, the same
    net/im/fm, just a different slice of the test log.
    """
    import pm4py

    train_names = [f"train{i}" for i in range(len(train_graphs))]
    train_log = _build_event_log(train_graphs, train_names)
    if train_log.empty:
        raise RuntimeError("训练集里没有任何可用的起点到终点路径，无法挖掘模型")

    if method == "pm4py_inductive":
        net, im, fm = pm4py.discover_petri_net_inductive(train_log)
    elif method == "pm4py_heuristics":
        net, im, fm = pm4py.discover_petri_net_heuristics(train_log)
    else:
        raise ValueError(f"unsupported pm4py method: {method}")

    test_log = _build_event_log(test_graphs, test_names)
    majority_profile = _majority_profile(train_graphs)
    sources = test_source_types or [None] * len(test_graphs)

    error_cases = []
    if not test_log.empty:
        for gi, (graph, name, source) in enumerate(zip(test_graphs, test_names, sources)):
            case_log = test_log[test_log["_case_group"] == gi]
            if case_log.empty:
                continue
            fitness, precision = _pm4py_fitness_precision(case_log, net, im, fm)
            f_measure = _f_measure(fitness, precision)
            if fitness < 0.6 or f_measure < 0.6:
                case = {
                    "workflow_name": name, "node_f1": round(fitness, 2), "edge_f1": round(f_measure, 2),
                    "structural_match": round(_structural_match(graph, majority_profile), 2),
                    "group": _mismatch_group(_structural_features(graph)),
                }
                if source is not None:
                    case["source_type"] = source
                error_cases.append(case)

    all_idxs = list(range(len(test_graphs)))
    metrics = _pm4py_metrics_for_indices(all_idxs, test_log, test_graphs, net, im, fm, majority_profile)

    metrics_by_source: dict[str, dict[str, float]] = {}
    if test_source_types:
        for source, idxs in _group_indices_by_source(test_source_types).items():
            metrics_by_source[source] = _pm4py_metrics_for_indices(idxs, test_log, test_graphs, net, im, fm, majority_profile)

    # Representative graph for display: play out the *actually discovered* model (not a
    # hand-picked medoid like run_consensus_dfg) and keep the shortest resulting trace, so the
    # displayed structure is genuinely derived from what pm4py mined, deterministically enough
    # to not flicker between runs of the same model.
    played = pm4py.play_out(net, im, fm)
    seqs = [[ev["concept:name"] for ev in tr] for tr in played if len(tr) > 0]
    consensus_seq = min(seqs, key=len) if seqs else []

    error_cases.sort(key=lambda c: c["node_f1"])
    return {
        "metrics": metrics,
        "metrics_by_source": metrics_by_source,
        "consensus_graph": _sequence_to_graph(consensus_seq),
        "error_analysis": error_cases[:10],
    }
