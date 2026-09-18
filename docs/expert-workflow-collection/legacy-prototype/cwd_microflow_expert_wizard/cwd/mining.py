from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from collections import Counter, defaultdict
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from .graph_utils import capability_edges_from_events

@dataclass
class DiscoveredWorkflow:
    cluster_id: int
    n_episodes: int
    nodes: List[str]
    edges: List[Tuple[str,str]]
    representative_sequence: List[str]
    miner: str = "consensus_dfg"
    model_repr: str = ""
    branch_types: Dict[str,str] = field(default_factory=dict)


def episode_table(df: pd.DataFrame, episode_col: str = "episode_pred") -> pd.DataFrame:
    rows = []
    for epi, g in df.sort_values(["case_id","timestamp"]).groupby(episode_col, sort=False):
        acts = [x for x in g["activity"].tolist() if x]
        roles = g["actor_role"].astype(str).tolist()
        dep_edges = sorted(capability_edges_from_events(g, "predecessor_event_ids", "activity"))
        branch_map = {}
        if "branch_type" in g.columns:
            for _, r in g.iterrows():
                bt = str(r.get("branch_type","") or "").lower().strip()
                role = str(r.get("control_role","") or "").lower().strip()
                if bt in {"and","xor","or"} and role in {"fork","join"}:
                    branch_map[str(r["activity"])] = bt
        rows.append({
            "episode_id": epi,
            "case_id": g["case_id"].iloc[0],
            "microflow_gt": g["microflow_gt"].mode().iloc[0] if "microflow_gt" in g else None,
            "activity_sequence": acts,
            "actor_sequence": roles,
            "dependency_edges": dep_edges,
            "branch_type_map": branch_map,
            "text": " ".join(acts + [f"ROLE_{r}" for r in roles]),
            "n_events": len(g),
        })
    return pd.DataFrame(rows)


def cluster_episodes(episodes, n_clusters=8, random_state=42):
    if episodes.empty:
        return episodes.assign(cluster=[]), {"silhouette": None}
    n_clusters = max(1, min(n_clusters, len(episodes)))
    vec = TfidfVectorizer(token_pattern=r"(?u)\b[\w_.-]+\b", ngram_range=(1,2))
    X = vec.fit_transform(episodes["text"])
    if n_clusters == 1:
        labels = np.zeros(len(episodes), dtype=int); km = None
    else:
        km = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=20)
        labels = km.fit_predict(X)
    out = episodes.copy(); out["cluster"] = labels
    sil = None
    if len(set(labels)) > 1 and len(out) > len(set(labels)):
        sil = float(silhouette_score(X, labels))
    return out, {"vectorizer": vec, "model": km, "silhouette": sil}


def mine_cluster_workflows(
    clustered: pd.DataFrame,
    miner: str = "consensus_dependency_graph",
    min_node_support: float = 0.45,
    min_edge_support: float = 0.35,
    inductive_noise_threshold: float = 0.0,
    heuristics_dependency_threshold: float = 0.5,
) -> List[DiscoveredWorkflow]:
    if miner == "consensus_dfg":
        return _mine_consensus(clustered, min_node_support, min_edge_support, dependency=False)
    if miner == "consensus_dependency_graph":
        return _mine_consensus(clustered, min_node_support, min_edge_support, dependency=True)
    if miner in ("pm4py_inductive", "pm4py_heuristics"):
        return _mine_pm4py(clustered, miner, inductive_noise_threshold, heuristics_dependency_threshold)
    raise ValueError(f"Unknown miner: {miner}")


def _mine_consensus(clustered, min_node_support, min_edge_support, dependency=False):
    result = []
    for cid, g in clustered.groupby("cluster"):
        seqs = g["activity_sequence"].tolist()
        node_counts, edge_counts = Counter(), Counter()
        branch_votes = defaultdict(Counter)
        seq_counter = Counter(tuple(s) for s in seqs)
        n = len(seqs)
        for _, row in g.iterrows():
            seq = row["activity_sequence"]
            node_counts.update(set(seq))
            edges = row.get("dependency_edges", []) if dependency else list(zip(seq[:-1],seq[1:]))
            edge_counts.update(set(tuple(x) for x in edges))
            for node, bt in (row.get("branch_type_map", {}) or {}).items():
                branch_votes[node][bt] += 1
        nodes = sorted([x for x,c in node_counts.items() if c/n >= min_node_support])
        edges = sorted([e for e,c in edge_counts.items() if c/n >= min_edge_support and e[0] in nodes and e[1] in nodes])
        representative = list(seq_counter.most_common(1)[0][0]) if seq_counter else []
        branch_types = {node:votes.most_common(1)[0][0] for node,votes in branch_votes.items() if node in nodes and votes}
        label = "consensus_dependency_graph" if dependency else "consensus_dfg"
        result.append(DiscoveredWorkflow(
            int(cid), n, nodes, edges, representative, miner=label,
            model_repr=f"{label}; node_support={min_node_support}; edge_support={min_edge_support}",
            branch_types=branch_types,
        ))
    return result


def _pm4py_event_df(cluster_rows: pd.DataFrame) -> pd.DataFrame:
    records = []
    for _, row in cluster_rows.iterrows():
        for pos, activity in enumerate(row["activity_sequence"]):
            records.append({
                "case:concept:name": str(row["episode_id"]),
                "concept:name": str(activity),
                "time:timestamp": pd.Timestamp("2026-01-01") + pd.Timedelta(seconds=pos)
            })
    return pd.DataFrame(records)


def _mine_pm4py(clustered, miner, inductive_noise_threshold, heuristics_dependency_threshold):
    try:
        import pm4py
    except ImportError as e:
        raise RuntimeError("PM4Py baseline requested but pm4py is not installed. Install requirements.txt first.") from e
    result = []
    for cid, g in clustered.groupby("cluster"):
        log_df = _pm4py_event_df(g)
        if log_df.empty: continue
        if miner == "pm4py_inductive":
            net, im, fm = pm4py.discover_petri_net_inductive(
                log_df, activity_key="concept:name", case_id_key="case:concept:name",
                timestamp_key="time:timestamp", noise_threshold=inductive_noise_threshold)
            repr_text = f"PM4Py Inductive Miner; noise_threshold={inductive_noise_threshold}"
        else:
            net, im, fm = pm4py.discover_petri_net_heuristics(
                log_df, activity_key="concept:name", case_id_key="case:concept:name",
                timestamp_key="time:timestamp", dependency_threshold=heuristics_dependency_threshold)
            repr_text = f"PM4Py Heuristics Miner; dependency_threshold={heuristics_dependency_threshold}"
        nodes, edges = _visible_transition_graph(net)
        seqs = g["activity_sequence"].tolist(); seq_counter = Counter(tuple(s) for s in seqs)
        representative = list(seq_counter.most_common(1)[0][0]) if seq_counter else []
        result.append(DiscoveredWorkflow(int(cid), len(g), sorted(nodes), sorted(edges), representative,
                                         miner=miner, model_repr=repr_text, branch_types={}))
    return result


def _visible_transition_graph(net):
    transitions = list(net.transitions); visible = [t for t in transitions if getattr(t,"label",None)]
    nodes = {str(t.label) for t in visible}; edges=set()
    def successors(start_t):
        frontier=[arc.target for arc in getattr(start_t,"out_arcs",[])]; visited=set(); found=set()
        while frontier:
            obj=frontier.pop(); oid=id(obj)
            if oid in visited: continue
            visited.add(oid)
            for arc in getattr(obj,"out_arcs",[]):
                nxt=arc.target; label=getattr(nxt,"label",None)
                if label: found.add(str(label))
                else:
                    for a2 in getattr(nxt,"out_arcs",[]): frontier.append(a2.target)
        return found
    for t in visible:
        for label in successors(t): edges.add((str(t.label),label))
    return nodes, edges
