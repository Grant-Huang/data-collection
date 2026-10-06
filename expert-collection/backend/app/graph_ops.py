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


def assign_missing_seqs(graph: dict) -> dict:
    """Gives every node lacking one a stable, human-facing step number (`seq`), counting up
    from the current max. This is the one thing a node's opaque `node_id` doesn't give either
    a person or the review-loop model: something short and ordinal to say out loud ("第3步").

    Assigned once, in list order, and never touched again -- not by a later edit, an insert
    before it, or a deletion elsewhere (see apply_ops: `update_node` only ever merges the given
    patch, which never contains `seq`). So numbers can end up with gaps after a deletion, and a
    node's number never matches its position in a topological read-back once the graph has been
    edited a few times -- both are accepted trade-offs for the number actually staying attached
    to the same node for the rest of a conversation, so "第3步" still means the same thing on
    turn 10 as it did on turn 2.

    Numbers are never reused either: `graph["next_seq"]` only ever goes up, so deleting the
    highest-numbered step and adding a new one gives the new step a fresh number. (Counting from
    "current max + 1" handed the deleted step's number to the new one, so an edited read-back
    or an expert's "第9步" written before the deletion would silently land on a different step.)
    """
    highest = max((n["seq"] for n in graph["nodes"] if isinstance(n.get("seq"), int)), default=0)
    next_seq = max(highest + 1, graph.get("next_seq") or 1)
    for n in graph["nodes"]:
        if not isinstance(n.get("seq"), int):
            n["seq"] = next_seq
            next_seq += 1
    graph["next_seq"] = next_seq
    return graph


def carry_seq_counter(restored: dict, current: dict) -> dict:
    """Restoring an earlier graph (undo, rollback to an earlier turn) must not rewind the number
    counter -- numbers handed out since then stay retired. Returns `restored`."""
    restored["next_seq"] = max(restored.get("next_seq") or 1, current.get("next_seq") or 1)
    return assign_missing_seqs(restored)


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
    sync_terminal_ids(graph)
    return assign_missing_seqs(graph)


def sync_terminal_ids(graph: dict) -> dict:
    """Keeps `start_node_ids` / `end_node_ids` in step with the nodes' own `node_type`.

    The lists used to be maintained only by explicit set_start/set_end ops, so any edit that
    changed a node's type (review_agent's update_node can turn the old end into an ordinary
    step and add a new end) or a model draft that returned `"start_node_ids": []` left them
    pointing at the wrong nodes. node_type is what the validator and the read-back go by, so
    it is the single source of truth here: existing order is kept, stale ids are dropped,
    missing ones appended.
    """
    for key, node_type in (("start_node_ids", "start"), ("end_node_ids", "end")):
        typed = [n["node_id"] for n in graph["nodes"] if n["node_type"] == node_type]
        kept = [i for i in graph.get(key, []) if i in typed]
        graph[key] = kept + [i for i in typed if i not in kept]
    return graph


# --- Shape helpers shared by draft normalization and edit repair ---------------------------
#
# "没头没尾" (a step that can't be reached from the start, or that leads nowhere) used to slip
# through because nothing looked at connectivity -- the validator only checked that a start and
# an end *exist*. The validator now reports it (dangling_head / dangling_tail); the two
# functions below fix the cases that have exactly one sensible reading, so the expert is only
# asked about the ones that genuinely need their answer.

def _outs(graph: dict, node_id: str) -> list[dict]:
    return [e for e in graph["edges"] if e["from"] == node_id]


def _ins(graph: dict, node_id: str) -> list[dict]:
    return [e for e in graph["edges"] if e["to"] == node_id]


def _new_id(graph: dict, prefix: str) -> str:
    taken = {n["node_id"] for n in graph["nodes"]} | {e["edge_id"] for e in graph["edges"]}
    i = 1
    while f"{prefix}{i}" in taken:
        i += 1
    return f"{prefix}{i}"


def _structural_edge(graph: dict, src: str, dst: str, edge_type: str = "normal",
                     condition: str | None = None, source_turn_ids: list[str] | None = None) -> dict:
    return {"edge_id": _new_id(graph, "auto_e"), "from": src, "to": dst, "edge_type": edge_type,
            "condition": condition, "confidence": 0.6, "expert_confirmed": False,
            "source_turn_ids": list(source_turn_ids or [])}


def break_cycles_into_retry(graph: dict) -> list[dict]:
    """Turns back-edges into retry_semantics, in place. Returns the removed edges.

    Models are told to express rework with retry_semantics, but still draw "不合格就回到 X"
    as an edge pointing back at X often enough; that used to fail the whole draft (or the
    whole regeneration) with cycle_detected. A back-edge found by DFS from the start nodes
    *is* exactly "from this step, go back to that earlier step", so it carries over losslessly
    to the documented representation. A node that already has retry_semantics keeps it.
    """
    removed: list[dict] = []
    while True:
        back = _find_back_edge(graph)
        if back is None:
            return removed
        graph["edges"] = [e for e in graph["edges"] if e["edge_id"] != back["edge_id"]]
        removed.append(back)
        node = _find_node(graph, back["from"])
        if node is not None and not (node.get("retry_semantics") or {}).get("enabled"):
            node["retry_semantics"] = {
                "enabled": True, "rework_reference_node_id": back["to"],
                "condition": back.get("condition") or None, "description": None,
            }


def _find_back_edge(graph: dict) -> dict | None:
    """One edge that closes a cycle (iterative DFS, start nodes first so "back" means
    "toward the start"), or None for a DAG."""
    order = [n["node_id"] for n in graph["nodes"] if n["node_type"] == "start"]
    order += [n["node_id"] for n in graph["nodes"] if n["node_id"] not in order]
    state: dict[str, int] = {}  # 1 = on the DFS stack, 2 = finished
    for root in order:
        if root in state:
            continue
        stack = [(root, iter(_outs(graph, root)))]
        state[root] = 1
        while stack:
            nid, it = stack[-1]
            edge = next(it, None)
            if edge is None:
                state[nid] = 2
                stack.pop()
                continue
            nxt = edge["to"]
            if state.get(nxt) == 1:
                return edge
            if nxt not in state and _find_node(graph, nxt) is not None:
                state[nxt] = 1
                stack.append((nxt, iter(_outs(graph, nxt))))
    return None


def add_missing_terminals(graph: dict, *, end_label: str = "结束") -> dict:
    """Gives a model-drafted graph a start / an end when it has none, in place.

    Only when the type is *entirely* missing, and only wired to what is unambiguous: a new
    start points at every node nothing leads into (by definition the first things done), a new
    end is reached from every node that leads nowhere (by definition the last things done).
    Isolated nodes are left alone -- the validator asks about those. Returns
    {"start": node_id|None, "end": node_id|None, "end_from": [labels]} so the caller can tell
    the expert what was assumed.
    """
    added = {"start": None, "end": None, "end_from": []}
    connected = {e["from"] for e in graph["edges"]} | {e["to"] for e in graph["edges"]}
    single = len(graph["nodes"]) == 1
    if graph["nodes"] and not any(n["node_type"] == "start" for n in graph["nodes"]):
        heads = [n for n in graph["nodes"] if not _ins(graph, n["node_id"])
                 and (n["node_id"] in connected or single) and n["node_type"] != "end"]
        if heads:
            sid = _new_id(graph, "auto_start")
            graph["nodes"].append({"node_id": sid, "node_type": "start", "label": "开始", "actor_roles": [],
                                   "confidence": 0.6, "expert_confirmed": False, "source_turn_ids": []})
            for h in heads:
                graph["edges"].append(_structural_edge(graph, sid, h["node_id"]))
            added["start"] = sid
    if graph["nodes"] and not any(n["node_type"] == "end" for n in graph["nodes"]):
        connected = {e["from"] for e in graph["edges"]} | {e["to"] for e in graph["edges"]}
        tails = [n for n in graph["nodes"] if not _outs(graph, n["node_id"])
                 and (n["node_id"] in connected or single) and n["node_type"] != "start"]
        if tails:
            eid = _new_id(graph, "auto_end")
            graph["nodes"].append({"node_id": eid, "node_type": "end", "label": end_label, "actor_roles": [],
                                   "confidence": 0.6, "expert_confirmed": False, "source_turn_ids": []})
            for t in tails:
                graph["edges"].append(_structural_edge(graph, t["node_id"], eid))
            added["end"] = eid
            added["end_from"] = [t["label"] for t in tails]
    sync_terminal_ids(graph)
    return added


def normalize_draft(graph: dict) -> dict:
    """Everything a freshly model-drafted graph (narrative extraction, 刷新工作流图) gets before
    anyone sees it: back-edges -> retry_semantics, missing start/end added, id lists synced.
    Returns add_missing_terminals' report plus "cycles" (the removed back-edges)."""
    cycles = break_cycles_into_retry(graph)
    report = add_missing_terminals(graph)
    report["cycles"] = cycles
    assign_missing_seqs(graph)
    return report


def rewire_after_edit(before: dict, after: dict, *, turn_id: str | None = None) -> dict:
    """Completes the wiring a conversational edit left half-done, in place on `after`.

    The review model is told "删掉中间步骤要把前后接上，插入步骤要改接原来的连线", but local
    models routinely emit just the remove_node / add_node + one edge. Applied literally, that
    splits the graph (the old "没头没尾"). Each repair below only fires where the model's ops
    leave exactly one sensible reading, and every added edge shows up in the change list
    (describe_changes diffs before/after), so the expert sees it:

    1. A removed step: a surviving predecessor that now leads nowhere is connected to the
       removed step's surviving successors (through a removed chain, if several consecutive
       steps went), keeping the type/condition of its old edge -- a decision's branch keeps
       its condition. Symmetrically, a surviving successor that nothing leads into any more
       is connected from the removed step's surviving predecessors.
    2. A decision that lost all but one branch because the steps of the other branches were
       removed is no longer a decision: it is dropped and its predecessors connected to the
       remaining branch.
    3. A new step wired on one side only, next to a node that before this edit had exactly
       one edge on that side: spliced in between ("A -> X" added while "A -> B" was kept
       becomes A -> X -> B; "X -> B" added while "A -> B" was kept becomes A -> X -> B).

    Anything else is left as it is; the validator reports it and the turn is refused.
    """
    b_ids = {n["node_id"] for n in before["nodes"]}
    a_ids = {n["node_id"] for n in after["nodes"]}
    removed, added = b_ids - a_ids, a_ids - b_ids
    stamp = [turn_id] if turn_id else []

    def has_edge(src: str, dst: str) -> bool:
        return any(e["from"] == src and e["to"] == dst for e in after["edges"])

    def reaches(src: str, dst: str) -> bool:
        seen, stack = {src}, [src]
        while stack:
            for e in _outs(after, stack.pop()):
                if e["to"] == dst:
                    return True
                if e["to"] not in seen:
                    seen.add(e["to"])
                    stack.append(e["to"])
        return False

    def link(src: str, dst: str, edge_type: str = "normal", condition: str | None = None) -> None:
        """Add src -> dst unless it already exists or would close a cycle (a repair must never
        make an edit worse, only finish it)."""
        if src != dst and not has_edge(src, dst) and not reaches(dst, src):
            after["edges"].append(_structural_edge(after, src, dst, edge_type, condition, stamp))

    def surviving(seeds: list[str], step) -> list[str]:
        """Follow `step` (successors or predecessors in `before`) through removed nodes until
        reaching nodes that still exist."""
        out, seen, queue = [], set(), list(seeds)
        while queue:
            nid = queue.pop(0)
            if nid in seen:
                continue
            seen.add(nid)
            if nid in a_ids:
                out.append(nid)
            elif nid in removed:
                queue += step(nid)
        return out

    def succ(nid: str) -> list[str]:
        return [e["to"] for e in _outs(before, nid)]

    def pred(nid: str) -> list[str]:
        return [e["from"] for e in _ins(before, nid)]

    def node_type(nid: str) -> str:
        return (_find_node(after, nid) or {}).get("node_type", "")

    # 1. bridge removed steps
    for e in before["edges"]:
        p, r = e["from"], e["to"]
        if r in removed and p in a_ids and node_type(p) != "end" and not _outs(after, p):
            for s in surviving([r], succ):
                if node_type(s) != "start":
                    link(p, s, e["edge_type"], e.get("condition"))
    for e in before["edges"]:
        r, s = e["from"], e["to"]
        if r in removed and s in a_ids and node_type(s) != "start" and not _ins(after, s):
            for p in surviving([r], pred):
                if node_type(p) != "end":
                    # Keep the type/condition of p's own edge into the removed chain, so a
                    # decision's branch still carries its condition after its first step goes.
                    old = next((x for x in _outs(before, p) if x["to"] in removed), None) or {}
                    link(p, s, old.get("edge_type", "normal"), old.get("condition"))

    # 2. collapse a decision whose other branches were all removed
    for d in [n for n in after["nodes"] if n["node_type"] == "decision" and n["node_id"] in b_ids]:
        did = d["node_id"]
        lost = [e for e in _outs(before, did) if e["to"] in removed]
        outs = _outs(after, did)
        if lost and len(_outs(before, did)) >= 2 and len(outs) == 1:
            target = outs[0]["to"]
            preds = _ins(after, did)
            after["nodes"] = [n for n in after["nodes"] if n["node_id"] != did]
            after["edges"] = [x for x in after["edges"] if did not in (x["from"], x["to"])]
            for pe in preds:
                link(pe["from"], target, pe["edge_type"], pe.get("condition"))
            a_ids.discard(did)

    # 3. splice a one-sided new step into the edge next to it
    for x in [n for n in after["nodes"] if n["node_id"] in added and n["node_type"] not in ("start", "end")]:
        xid = x["node_id"]
        ins, outs = _ins(after, xid), _outs(after, xid)
        if len(ins) == 1 and not outs:
            p = ins[0]["from"]
            old = [e for e in _outs(before, p) if e["to"] in a_ids]
            if len(_outs(before, p)) == 1 and len(old) == 1 and has_edge(p, old[0]["to"]) \
                    and not reaches(old[0]["to"], xid):
                s = old[0]["to"]
                after["edges"] = [e for e in after["edges"] if not (e["from"] == p and e["to"] == s)]
                link(xid, s)
        elif len(outs) == 1 and not ins:
            s = outs[0]["to"]
            old = [e for e in _ins(before, s) if e["from"] in a_ids]
            if len(_ins(before, s)) == 1 and len(old) == 1 and has_edge(old[0]["from"], s) \
                    and not reaches(xid, old[0]["from"]):
                p, kept = old[0]["from"], old[0]
                after["edges"] = [e for e in after["edges"] if not (e["from"] == p and e["to"] == s)]
                link(p, xid, kept["edge_type"], kept.get("condition"))
    sync_terminal_ids(after)
    return after
