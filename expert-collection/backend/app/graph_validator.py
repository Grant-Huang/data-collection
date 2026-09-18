"""Graph Validator -- PRD sections 3.3/3.4/12.2.1/17: pure rule-based structural checks, no LLM
(section 15.3 explicitly lists this as a "does not need LLM" item, to keep it reproducible).
"""
from __future__ import annotations

from typing import Any


def validate(graph: dict[str, Any]) -> list[dict[str, str]]:
    """Returns a list of {level, code, message, node_id?, edge_id?} issues. Empty list = valid."""
    issues: list[dict[str, str]] = []
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    node_ids = [n["node_id"] for n in nodes]
    node_by_id = {n["node_id"]: n for n in nodes}

    # ID uniqueness
    seen: set[str] = set()
    for nid in node_ids:
        if nid in seen:
            issues.append(_err("duplicate_node_id", f"节点 id 重复：{nid}", node_id=nid))
        seen.add(nid)
    seen = set()
    for e in edges:
        if e["edge_id"] in seen:
            issues.append(_err("duplicate_edge_id", f"边 id 重复：{e['edge_id']}", edge_id=e["edge_id"]))
        seen.add(e["edge_id"])

    # Edge endpoints must exist
    for e in edges:
        if e["from"] not in node_by_id:
            issues.append(_err("dangling_edge", f"边 {e['edge_id']} 的起点 {e['from']} 不存在", edge_id=e["edge_id"]))
        if e["to"] not in node_by_id:
            issues.append(_err("dangling_edge", f"边 {e['edge_id']} 的终点 {e['to']} 不存在", edge_id=e["edge_id"]))

    # DAG check: must be acyclic and every edge endpoint must resolve (topo sort)
    if not issues:
        cycle_node = _find_cycle(node_ids, edges)
        if cycle_node:
            issues.append(_err(
                "cycle_detected",
                f"检测到环，涉及节点 {cycle_node}——返工/重试请用 retry_semantics，不要建反向边（PRD 7.1 节）",
                node_id=cycle_node,
            ))

    # Start / end
    starts = [n for n in nodes if n["node_type"] == "start"]
    ends = [n for n in nodes if n["node_type"] == "end"]
    if nodes and not starts:
        issues.append(_err("missing_start", "缺少 start 节点"))
    if nodes and not ends:
        issues.append(_err("missing_end", "缺少 end 节点"))
    incoming_count: dict[str, int] = {}
    outgoing_count: dict[str, int] = {}
    for e in edges:
        outgoing_count[e["from"]] = outgoing_count.get(e["from"], 0) + 1
        incoming_count[e["to"]] = incoming_count.get(e["to"], 0) + 1
    for n in starts:
        if incoming_count.get(n["node_id"], 0) > 0:
            issues.append(_err("start_has_incoming", "start 节点不允许有入边", node_id=n["node_id"]))
    for n in ends:
        if outgoing_count.get(n["node_id"], 0) > 0:
            issues.append(_err("end_has_outgoing", "end 节点不允许有出边", node_id=n["node_id"]))

    # Decision: >=2 outgoing conditional edges, conditions non-empty
    for n in nodes:
        if n["node_type"] == "decision":
            out = [e for e in edges if e["from"] == n["node_id"] and e["edge_type"] == "conditional"]
            if len(out) < 2:
                issues.append(_err(
                    "decision_needs_two_branches",
                    f"判断节点「{n['label']}」至少需要两条 conditional 出边，当前 {len(out)} 条",
                    node_id=n["node_id"],
                ))
            for e in out:
                if not (e.get("condition") or "").strip():
                    issues.append(_warn("empty_condition", f"分支边 {e['edge_id']} 缺少具体条件", edge_id=e["edge_id"]))

    # parallel_split: >=2 outgoing parallel edges
    for n in nodes:
        if n["node_type"] == "parallel_split":
            out = [e for e in edges if e["from"] == n["node_id"] and e["edge_type"] == "parallel"]
            if len(out) < 2:
                issues.append(_err(
                    "parallel_split_needs_two",
                    f"并行拆分节点「{n['label']}」至少需要两条 parallel 出边，当前 {len(out)} 条",
                    node_id=n["node_id"],
                ))

    # parallel_join: >=2 incoming parallel/merge edges
    for n in nodes:
        if n["node_type"] == "parallel_join":
            inc = [e for e in edges if e["to"] == n["node_id"] and e["edge_type"] in ("parallel", "merge")]
            if len(inc) < 2:
                issues.append(_err(
                    "parallel_join_needs_two",
                    f"并行汇合节点「{n['label']}」至少需要两条入边，当前 {len(inc)} 条",
                    node_id=n["node_id"],
                ))

    # merge: >=2 incoming edges
    for n in nodes:
        if n["node_type"] == "merge":
            inc = [e for e in edges if e["to"] == n["node_id"]]
            if len(inc) < 2:
                issues.append(_err(
                    "merge_needs_two",
                    f"汇合节点「{n['label']}」至少需要两条入边，当前 {len(inc)} 条",
                    node_id=n["node_id"],
                ))

    # No isolated nodes (once there's more than one node)
    if len(nodes) > 1:
        connected = set(incoming_count) | set(outgoing_count)
        for n in nodes:
            if n["node_id"] not in connected:
                issues.append(_err("isolated_node", f"节点「{n['label']}」没有任何连线", node_id=n["node_id"]))

    return issues


def is_valid(graph: dict[str, Any]) -> bool:
    return not any(i["level"] == "error" for i in validate(graph))


def _find_cycle(node_ids: list[str], edges: list[dict]) -> str | None:
    """Kahn's algorithm; returns one node id that's part of a cycle, or None if acyclic."""
    indeg = {nid: 0 for nid in node_ids}
    adjacency: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for e in edges:
        if e["from"] in adjacency and e["to"] in indeg:
            adjacency[e["from"]].append(e["to"])
            indeg[e["to"]] += 1
    queue = [nid for nid, d in indeg.items() if d == 0]
    visited = 0
    while queue:
        nid = queue.pop()
        visited += 1
        for nxt in adjacency[nid]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    if visited < len(node_ids):
        remaining = [nid for nid, d in indeg.items() if d > 0]
        return remaining[0] if remaining else None
    return None


def _err(code: str, message: str, node_id: str | None = None, edge_id: str | None = None) -> dict:
    return {"level": "error", "code": code, "message": message, "node_id": node_id, "edge_id": edge_id}


def _warn(code: str, message: str, node_id: str | None = None, edge_id: str | None = None) -> dict:
    return {"level": "warning", "code": code, "message": message, "node_id": node_id, "edge_id": edge_id}
