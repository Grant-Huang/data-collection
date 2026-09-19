"""Experiment Center execution engine -- PRD 14, honestly scoped per IMPLEMENTATION_PLAN.md
section 7: this product's graphs are produced directly by structured conversation, not
extracted from raw text against a separate Gold standard, so most of PRD 14.3's metrics
(which assume a Gold annotation to compare against) have no real ground truth to compute
against here. Only `consensus_dfg` actually runs, and only computes metrics that are
genuinely derivable without Gold annotations: a train/test split where the "prediction" is a
consensus structure mined (real Directly-Follows Graph mining, hence the name) from the
train split, evaluated against the held-out test split.

Other methods (`pm4py_inductive`, `pm4py_heuristics`, `llm_extractor`) are real, selectable
options in the create-experiment form (matching the PRD's field design) but have no execution
engine wired up this round -- running one fails honestly rather than faking numbers.
"""
from __future__ import annotations

import random
from typing import Any

NODE_TYPE_LABEL = {
    "start": "起点", "end": "终点", "activity": "活动", "wait": "等待",
    "decision": "判断", "parallel_split": "并行拆分", "parallel_join": "并行汇合",
    "merge": "汇合", "approval": "审批", "handoff": "交接",
}

IMPLEMENTED_METHODS = {"consensus_dfg"}


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


def run_consensus_dfg(train_graphs: list[dict], test_graphs: list[dict], test_names: list[str]) -> dict[str, Any]:
    train_seqs = [s for s in (_main_path_types(g) for g in train_graphs) if s]
    consensus_seq = _pick_medoid_sequence(train_seqs)
    consensus_bigrams = _bigrams(consensus_seq)
    consensus_types = set(consensus_seq)

    train_feats = [_structural_features(g) for g in train_graphs]
    majority_profile = (
        {k: sum(f[k] for f in train_feats) > len(train_feats) / 2 for k in train_feats[0]}
        if train_feats else {}
    )

    node_f1s, edge_f1s = [], []
    error_cases = []
    for graph, name in zip(test_graphs, test_names):
        test_seq = _main_path_types(graph)
        test_types = set(test_seq)
        test_bigrams = _bigrams(test_seq)
        _, _, node_f1 = _prf(consensus_types, test_types)
        _, _, edge_f1 = _prf(consensus_bigrams, test_bigrams)
        node_f1s.append(node_f1)
        edge_f1s.append(edge_f1)

        feats = _structural_features(graph)
        structural_match = sum(1 for k in majority_profile if majority_profile[k] == feats.get(k)) / len(majority_profile) if majority_profile else 1.0

        if node_f1 < 0.6 or edge_f1 < 0.6:
            mismatch_group = "含分支" if feats["has_decision"] else "含并行" if feats["has_parallel"] else "含返工" if feats["has_retry"] else "线性"
            error_cases.append({
                "workflow_name": name, "node_f1": round(node_f1, 2), "edge_f1": round(edge_f1, 2),
                "structural_match": round(structural_match, 2), "group": mismatch_group,
            })

    def _avg(vals: list[float]) -> float:
        return round(sum(vals) / len(vals), 3) if vals else 0.0

    metrics = {
        "node_f1": _avg(node_f1s),
        "edge_f1": _avg(edge_f1s),
        "graph_structural_f1": _avg(edge_f1s),  # bigram overlap doubles as the graph-level proxy here
        "structural_match_rate": _avg([
            sum(1 for k in majority_profile if majority_profile[k] == _structural_features(g).get(k)) / len(majority_profile)
            if majority_profile else 1.0
            for g in test_graphs
        ]),
    }
    error_cases.sort(key=lambda c: c["node_f1"])
    return {
        "metrics": metrics,
        "consensus_graph": _sequence_to_graph(consensus_seq),
        "error_analysis": error_cases[:10],
    }
