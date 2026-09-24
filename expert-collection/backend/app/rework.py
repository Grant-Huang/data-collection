"""Rework edits -- apply an annotator's node verdicts / a reworker's edits to a record graph,
producing the corrected graph that goes back into independent review (decision 9: "需要修改"
must actually produce a corrected graph and go through a Rework loop, not just store notes).

Pure functions over plain graph dicts (same shape graph_ops.py / graph_validator.py use), no
database access, so both routers/annotations.py and tests can call them directly.

Edits shape (one object for both uses -- an annotator's `node_verdicts` is just the subset
without renames/inserts, which is why the reworker can start from any annotator's suggestion
verbatim):

    {
      "node_verdicts": {"<node_id>": "keep" | "delete" | "merge_into:<predecessor_id>"},
      "renames": {"<node_id>": "<new label>"},
      "inserts": [{"after": "<node_id>", "label": "<label>"}],
    }

Application order is fixed -- merges, deletes, inserts, renames -- so structural judgements
are applied to the graph the annotators actually saw (an inserted step must not become a
merge source's predecessor), and a rename of a merge target replaces the combined
"A；B" label. Every reference is checked against the *input* graph first, so an edit set
either applies cleanly or raises EditError with a message the UI can show as-is. Structural validity of the *result* (cycles,
decision branch counts, ...) is not re-derived here: callers run graph_validator on the output,
the same validator import and expert collection already use.
"""
from __future__ import annotations

import copy
from typing import Any

# Node types whose outgoing edges carry branch semantics -- "insert a step after" such a node
# is ambiguous (which branch?), so it's refused with a hint to insert on the branch instead.
_BRANCHING_TYPES = {"decision", "parallel_split"}
_TERMINAL_TYPES = {"start", "end"}


class EditError(ValueError):
    """An edit that can't be applied to this graph (unknown node, illegal target, ...)."""


def predecessors(graph: dict, node_id: str) -> list[str]:
    """Real graph predecessors (edge sources pointing at node_id), in edge order, deduped.
    "合并进上一个节点" means one of these -- never list order, which for a branching DAG
    isn't a predecessor at all (the bug this replaces).
    """
    seen: list[str] = []
    for e in graph.get("edges", []):
        if e["to"] == node_id and e["from"] not in seen:
            seen.append(e["from"])
    return seen


def parse_verdict(value: str) -> tuple[str, str | None]:
    """"merge_into:n3" -> ("merge_into", "n3"); "keep"/"delete" -> (value, None)."""
    if value.startswith("merge_into:"):
        return "merge_into", value.split(":", 1)[1]
    return value, None


def validate_edits(graph: dict, edits: dict) -> None:
    """Raises EditError if `edits` references anything illegal for `graph`. Runs entirely
    against the input graph so the checks don't depend on application order.
    """
    nodes = {n["node_id"]: n for n in graph.get("nodes", [])}

    def _node(nid: str, what: str) -> dict:
        if nid not in nodes:
            raise EditError(f"{what}引用的节点 {nid} 不在当前图里")
        return nodes[nid]

    verdicts = edits.get("node_verdicts") or {}
    deleted = set()
    for nid, value in verdicts.items():
        node = _node(nid, "节点判定")
        kind, target = parse_verdict(value)
        if kind == "keep":
            continue
        if kind not in ("delete", "merge_into"):
            raise EditError(f"节点「{node['label']}」的判定值无法识别：{value}")
        if node["node_type"] in _TERMINAL_TYPES:
            raise EditError(f"开始/结束节点「{node['label']}」不能删除或合并")
        if kind == "delete":
            deleted.add(nid)
        else:
            _node(target, "合并目标")
            if target not in predecessors(graph, nid):
                raise EditError(f"节点「{node['label']}」只能合并进它在图上的前驱节点，{target} 不是它的前驱")
    for nid, value in verdicts.items():
        kind, target = parse_verdict(value)
        if kind == "merge_into" and target in deleted:
            raise EditError(f"节点「{nodes[nid]['label']}」要合并进的节点「{nodes[target]['label']}」已被标记为删除")

    merged_away = {nid for nid, v in verdicts.items() if parse_verdict(v)[0] == "merge_into"}
    for nid, label in (edits.get("renames") or {}).items():
        _node(nid, "改名")
        if nid in deleted or nid in merged_away:
            raise EditError(f"节点「{nodes[nid]['label']}」已被删除或合并，不能改名（要改合并后的名称，请改它合并进去的那个节点）")
        if not (label or "").strip():
            raise EditError(f"节点 {nid} 的新名称不能为空")

    for ins in edits.get("inserts") or []:
        after = _node(ins.get("after", ""), "插入位置")
        if not (ins.get("label") or "").strip():
            raise EditError(f"在「{after['label']}」之后插入的步骤名称不能为空")
        if after["node_type"] == "end":
            raise EditError("不能在结束节点之后插入步骤")
        if after["node_type"] in _BRANCHING_TYPES:
            raise EditError(f"「{after['label']}」是分支/并行拆分节点，请在具体某条分支上的节点之后插入")
        if after["node_id"] in deleted:
            raise EditError(f"「{after['label']}」已被标记为删除，不能在它之后插入")


def _unique_id(prefix: str, taken: set[str]) -> str:
    i = 1
    while f"{prefix}{i}" in taken:
        i += 1
    new_id = f"{prefix}{i}"
    taken.add(new_id)
    return new_id


def _add_edge(graph: dict, taken_edge_ids: set[str], src: str, dst: str, template: dict | None) -> None:
    """Adds src->dst unless it already exists or would be a self-loop. Carries edge_type /
    condition over from `template` so a branch condition survives a node being bypassed.
    """
    if src == dst or any(e["from"] == src and e["to"] == dst for e in graph["edges"]):
        return
    edge = {"edge_id": _unique_id("re", taken_edge_ids), "from": src, "to": dst,
            "edge_type": (template or {}).get("edge_type", "normal")}
    if template and template.get("condition"):
        edge["condition"] = template["condition"]
    graph["edges"].append(edge)


def _remove_node(graph: dict, nid: str) -> None:
    graph["nodes"] = [n for n in graph["nodes"] if n["node_id"] != nid]
    graph["edges"] = [e for e in graph["edges"] if e["from"] != nid and e["to"] != nid]
    for key in ("start_node_ids", "end_node_ids"):
        if key in graph:
            graph[key] = [x for x in graph[key] if x != nid]


def apply_edits(graph: dict, edits: dict, *, new_node_prefix: str = "rw") -> dict[str, Any]:
    """Returns a new graph (input untouched) with `edits` applied. Raises EditError."""
    validate_edits(graph, edits)
    g = copy.deepcopy(graph)
    g.setdefault("edges", [])
    node_by_id = {n["node_id"]: n for n in g["nodes"]}
    taken_nodes = set(node_by_id)
    taken_edges = {e["edge_id"] for e in g["edges"]}

    verdicts = edits.get("node_verdicts") or {}

    # 1. merges, resolved through an alias map so "C into B, B into A" ends up all in A.
    alias: dict[str, str] = {}

    def resolve(nid: str) -> str:
        while nid in alias:
            nid = alias[nid]
        return nid

    # Process in the input graph's node order; chained merges are handled by `resolve`.
    for n in graph["nodes"]:
        kind, target = parse_verdict(verdicts.get(n["node_id"], "keep"))
        if kind != "merge_into":
            continue
        src, dst = n["node_id"], resolve(target)
        dst_node = node_by_id[dst]
        dst_node["label"] = f"{dst_node['label']}；{node_by_id[src]['label']}"
        for e in list(g["edges"]):
            if e["from"] == src:
                _add_edge(g, taken_edges, dst, e["to"], e)
            elif e["to"] == src and e["from"] != dst:
                _add_edge(g, taken_edges, e["from"], dst, e)
        _remove_node(g, src)
        alias[src] = dst

    # 2. deletes: bypass the node -- every predecessor connects to every successor, keeping
    # the incoming edge's type/condition (so a decision's branch condition isn't lost).
    for n in graph["nodes"]:
        if parse_verdict(verdicts.get(n["node_id"], "keep"))[0] != "delete":
            continue
        nid = n["node_id"]
        incoming = [e for e in g["edges"] if e["to"] == nid]
        outgoing = [e for e in g["edges"] if e["from"] == nid]
        for ie in incoming:
            for oe in outgoing:
                _add_edge(g, taken_edges, ie["from"], oe["to"], ie)
        _remove_node(g, nid)

    # 3. inserts: the new step takes over all of `after`'s outgoing edges, then after -> new.
    # "after" a merged-away node means after the node it was merged into.
    for ins in edits.get("inserts") or []:
        after = resolve(ins["after"])
        new_id = _unique_id(new_node_prefix, taken_nodes)
        new_node = {"node_id": new_id, "node_type": "activity", "label": ins["label"].strip(), "actor_roles": []}
        g["nodes"].append(new_node)
        node_by_id[new_id] = new_node
        for e in g["edges"]:
            if e["from"] == after:
                e["from"] = new_id
        g["edges"].append({"edge_id": _unique_id("re", taken_edges), "from": after, "to": new_id, "edge_type": "normal"})

    # 4. renames last, so renaming a merge target replaces the combined "A；B" label.
    for nid, label in (edits.get("renames") or {}).items():
        node_by_id[nid]["label"] = label.strip()

    return g
