"""Graph Ops: the shared change protocol from PRD section 16 ("LLM 修改与人工修改共用一套变更协议").

Operates on the graph as a plain dict (nodes: list[dict], edges: list[dict], start_node_ids,
end_node_ids) so both the mock/real guide service and any future manual-edit endpoint can emit
the same op list and go through the same apply function.
"""
from __future__ import annotations

from typing import Any


def new_graph() -> dict[str, Any]:
    return {"graph_type": "dag", "start_node_ids": [], "end_node_ids": [], "nodes": [], "edges": []}


def _find_node(graph: dict, node_id: str) -> dict | None:
    return next((n for n in graph["nodes"] if n["node_id"] == node_id), None)


def _find_edge(graph: dict, edge_id: str) -> dict | None:
    return next((e for e in graph["edges"] if e["edge_id"] == edge_id), None)


def apply_ops(graph: dict, ops: list[dict]) -> dict:
    """Applies a list of Graph Ops in order, mutating and returning the same graph dict.

    Unknown op types are ignored rather than raising -- a guide-service bug that emits a
    malformed op shouldn't take the whole turn down; it just won't have any effect, and the
    validator will catch whatever structural problem results (PRD 3.4: never silently patch
    around a problem, but also never let one bad op corrupt turns after it).
    """
    for op in ops:
        kind = op.get("op")
        if kind == "add_node":
            node = op["node"]
            if not _find_node(graph, node["node_id"]):
                graph["nodes"].append(node)
        elif kind == "update_node":
            node = _find_node(graph, op["node_id"])
            if node:
                node.update(op.get("patch", {}))
        elif kind == "remove_node":
            graph["nodes"] = [n for n in graph["nodes"] if n["node_id"] != op["node_id"]]
            graph["edges"] = [
                e for e in graph["edges"] if e["from"] != op["node_id"] and e["to"] != op["node_id"]
            ]
            graph["start_node_ids"] = [n for n in graph["start_node_ids"] if n != op["node_id"]]
            graph["end_node_ids"] = [n for n in graph["end_node_ids"] if n != op["node_id"]]
        elif kind == "add_edge":
            edge = op["edge"]
            if not _find_edge(graph, edge["edge_id"]):
                graph["edges"].append(edge)
        elif kind == "update_edge":
            edge = _find_edge(graph, op["edge_id"])
            if edge:
                edge.update(op.get("patch", {}))
        elif kind == "remove_edge":
            graph["edges"] = [e for e in graph["edges"] if e["edge_id"] != op["edge_id"]]
        elif kind == "set_start":
            if op["node_id"] not in graph["start_node_ids"]:
                graph["start_node_ids"].append(op["node_id"])
        elif kind == "set_end":
            if op["node_id"] not in graph["end_node_ids"]:
                graph["end_node_ids"].append(op["node_id"])
        elif kind == "set_retry_semantics":
            node = _find_node(graph, op["node_id"])
            if node:
                node["retry_semantics"] = op["retry_semantics"]
    return graph
