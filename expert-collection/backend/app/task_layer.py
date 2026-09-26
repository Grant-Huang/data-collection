"""Task Workflow DAG (the upper layer of the dual-DAG model -- IMPLEMENTATION_PLAN.md section 18):
"谁负责哪一段、任务之间怎么交接", built from the same single expert conversation that already
produces the step-level graph (which is, in the dual-DAG model's terms, the SOP / Skill DAG:
"每一段具体怎么做").

Where the task layer comes from -- the priority the product owner set for this:
1. The expert defines it directly (most reliable; this module) -- the conversation asks one
   extra question at the end ("按负责方分成哪几个任务？") and then asks, per task, which
   already-described step it starts from. Both answers are the expert's own words / picks.
2. An LLM mines it from real work logs (most important long-term, NOT this module -- that's
   the dual-DAG design doc's §26 P2 "WorkEvent -> Pattern Detection" item, out of scope this
   iteration).
3. The system infers it from owner / org structure -- auxiliary only, never allowed to define
   the DAG by itself. This module deliberately does NOT group steps by `actor_roles` on its
   own: the step graph barely carries roles (only approval nodes do), and even when it does,
   "who's responsible" is not the same decision as "where does one task end".

The LLM's role here is the same as in guide_service's step parsing: it only *structures* what
the expert typed (split the outline into items, separate owner from task name). It never
invents a task, an owner or a boundary. Any LLM failure falls back to a rule-based parser over
a closed set of separators, same pattern as `guide_service._understand_step`.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from . import llm_client
from . import settings as app_settings

TASK_OUTLINE_QUESTION = (
    "最后一个问题：如果把整件事按「谁负责哪一段」分成几个任务，你会怎么分？"
    "按先后顺序说，每项最好写成「负责方：做什么」，比如：客服：确认问题 → 质量部：复检 → 生产部：处理。"
)
# Prefill chip (PRD 18: fills the draft box, never auto-sends).
SINGLE_TASK_CHIP = "整件事就一个任务"
# Offered alongside the step candidates on every boundary question -- a task the expert
# names at the top level but never described step by step (e.g. "客服回复客户") is real and
# common, and forcing it onto some step would fabricate a mapping the expert never made.
NO_STEP_CHIP = "（这个任务没有对应的步骤）"

MAX_TASKS = 8

# Node types that carry expert-described content and so can be picked as "this task starts
# here". Structural nodes (start/decision/parallel_*/merge/end) are never offered -- they have
# no label the expert would recognize as a step they described.
_STEP_NODE_TYPES = {"activity", "approval", "wait", "handoff"}


def _nid() -> str:
    return uuid.uuid4().hex[:8]


# --- Outline parsing -----------------------------------------------------------------------

# Strong separators: if the expert used any of these, trust them exclusively and don't also
# split on commas (a comma inside one item, e.g. "客服：确认问题，记录投诉", is then kept).
_STRONG_SEP_RE = re.compile(r"\s*(?:→|->|=>|—>|＞|>|；|;|\n)\s*")
# Weak separators, only used when no strong separator is present at all.
_WEAK_SEP_RE = re.compile(r"\s*(?:，|,|、|。|然后|接着|之后|最后)\s*")
# Repeated, so stacked fillers like "先由" are both stripped.
_ITEM_FILLER_RE = re.compile(r"^(?:(?:首先|先|再由|再|然后|接着|之后|最后|由)\s*)+")
_OWNER_COLON_RE = re.compile(r"^(.{1,12}?)[：:]\s*(.+)$")
_OWNER_RESPONSIBLE_RE = re.compile(r"^(.{1,12}?)负责\s*(.+)$")


def _rule_parse_outline(text: str) -> list[dict[str, Any]]:
    """Split on a closed set of separators and read "负责方：做什么" / "X负责Y" off each item.
    No NLU: an item that matches neither pattern keeps its whole text as the task name with no
    owner -- an honest "not stated" rather than a guessed owner.
    """
    splitter = _STRONG_SEP_RE if _STRONG_SEP_RE.search(text) else _WEAK_SEP_RE
    items = []
    for raw in splitter.split(text.strip()):
        item = _ITEM_FILLER_RE.sub("", raw.strip("，,。 ")).strip()
        if not item:
            continue
        owner, name = None, item
        m = _OWNER_COLON_RE.match(item) or _OWNER_RESPONSIBLE_RE.match(item)
        if m and m.group(2).strip():
            owner, name = m.group(1).strip(), m.group(2).strip()
        items.append({"name": name[:40], "owner": owner[:20] if owner else None})
    return items[:MAX_TASKS]


_OUTLINE_SYSTEM_PROMPT = """你是一个制造业专家访谈助手的解析模块，只负责把专家对"这件事按负责方分成哪几个任务"的回答解析成结构化 JSON，不做总结、改写，也不能编造专家没说过的任务或负责方。

只输出一个 JSON object，字段：
- "tasks"：数组，按专家说的先后顺序排列。每个元素：
  - "name"：这个任务做什么，用专家自己的措辞（可以去掉"先""然后"这类时序填充词）。
  - "owner"：负责这个任务的部门/岗位/角色，必须是专家原话里出现过的词；专家没说谁负责就填 null，不要猜。

只输出 JSON，不要有任何其他文字。"""


def _llm_parse_outline(text: str, slot_config: dict) -> list[dict[str, Any]] | None:
    """Returns None on ANY failure so the caller falls back to `_rule_parse_outline` -- never
    raises (llm_client.py's "must not crash or hang the turn" rule).
    """
    try:
        parsed = llm_client.chat_completion_json(slot_config, [
            {"role": "system", "content": _OUTLINE_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ])
    except llm_client.LLMError:
        return None

    tasks = parsed.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return None
    items = []
    for t in tasks[:MAX_TASKS]:
        if not isinstance(t, dict):
            return None
        name = t.get("name")
        if not isinstance(name, str) or not name.strip():
            return None
        owner = t.get("owner")
        # Cheap anti-fabrication guard: an owner the expert never actually said is dropped
        # back to "not stated" instead of being trusted.
        if not isinstance(owner, str) or not owner.strip() or owner.strip() not in text:
            owner = None
        items.append({"name": name.strip()[:40], "owner": owner.strip()[:20] if owner else None})
    return items


def parse_outline(text: str) -> tuple[list[dict[str, Any]], str]:
    """Returns (items, structured_by) where each item is {"name", "owner"} and structured_by
    is "llm" or "rule" -- recorded on every task so a dataset consumer can tell the two apart.
    """
    slot_config = app_settings.resolve_slot_for_call(app_settings.get_effective_settings(), "guide_service")
    if slot_config.get("enabled") and slot_config.get("endpoint") and slot_config.get("model_name"):
        items = _llm_parse_outline(text, slot_config)
        if items:
            return items, "llm"
    return _rule_parse_outline(text), "rule"


# --- Step -> task boundaries ---------------------------------------------------------------

def ordered_node_ids(graph: dict) -> list[str]:
    """Topological order of the step graph, ties broken by creation order. Creation order alone
    is not enough: the structural sweeps insert decision/approval nodes *after* an existing step
    but append them to the end of `nodes`. Retry is recorded as `retry_semantics`, not a back
    edge, so the graph is a DAG; any node left over by an unexpected cycle is appended in
    creation order rather than dropped.
    """
    nodes = graph.get("nodes", [])
    ids = [n["node_id"] for n in nodes]
    rank = {nid: i for i, nid in enumerate(ids)}
    indeg = {nid: 0 for nid in ids}
    succ: dict[str, list[str]] = {nid: [] for nid in ids}
    for e in graph.get("edges", []):
        if e["from"] in indeg and e["to"] in indeg:
            succ[e["from"]].append(e["to"])
            indeg[e["to"]] += 1
    ready = sorted((nid for nid in ids if indeg[nid] == 0), key=rank.get)
    order: list[str] = []
    while ready:
        nid = ready.pop(0)
        order.append(nid)
        for nxt in succ[nid]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                ready.append(nxt)
        ready.sort(key=rank.get)
    seen = set(order)
    return order + [nid for nid in ids if nid not in seen]


def step_candidates(graph: dict, prior_starts: list[str]) -> dict[str, str]:
    """Chip label -> node_id for every content step strictly after the last of `prior_starts`
    in graph order. Duplicate labels get a "（第 n 步）" suffix so every chip maps back to
    exactly one node.
    """
    order = ordered_node_ids(graph)
    pos = {nid: i for i, nid in enumerate(order)}
    after = max((pos[s] for s in prior_starts if s in pos), default=-1)
    by_id = {n["node_id"]: n for n in graph.get("nodes", [])}
    options: dict[str, str] = {}
    seen: dict[str, int] = {}
    step_no = 0
    for i, nid in enumerate(order):
        node = by_id[nid]
        if node.get("node_type") not in _STEP_NODE_TYPES:
            continue
        step_no += 1
        if i <= after:
            continue
        label = node.get("label") or "（未命名步骤）"
        seen[label] = seen.get(label, 0) + 1
        chip = label if seen[label] == 1 else f"{label}（第 {step_no} 步）"
        options[chip] = nid
    return options


def boundary_question(items: list[dict[str, Any]], task_index: int) -> str:
    item = items[task_index]
    owner = f"（{item['owner']}）" if item.get("owner") else ""
    return f"「{item['name']}」{owner}是从哪一步开始的？"


def build_task_workflow(graph: dict, items: list[dict[str, Any]], starts: list[str | None],
                         structured_by: str) -> dict[str, Any]:
    """`starts[i]` is the node_id task i starts at, or None when the expert said that task has
    no described steps. Task 0 always starts at the beginning of the graph (starts[0] is
    ignored). Every SOP node, in graph order, belongs to the task whose start comes last at or
    before it; a task with no start gets no nodes.

    Returns {"graph": <a plain Graph dict>, "tasks": [...]}: the task layer is itself a normal
    Graph (start -> task nodes -> end) so the exact same DagView / validator / export paths
    already built for the step graph work on it unchanged. Task name lives in the node's
    `label`, owner in its `actor_roles` -- not duplicated into `tasks`, so export anonymization
    (which already walks node labels/roles) covers the task layer with no extra rules.
    """
    order = ordered_node_ids(graph)
    pos = {nid: i for i, nid in enumerate(order)}
    begin = [(0, 0)] + [(pos[s], i) for i, s in enumerate(starts) if i > 0 and s in pos]
    begin.sort()
    sop_ids: list[list[str]] = [[] for _ in items]
    for i, nid in enumerate(order):
        owner_task = max((b for b in begin if b[0] <= i), default=(0, 0))[1]
        sop_ids[owner_task].append(nid)

    confidence = 0.8 if structured_by == "llm" else 0.9
    start_id, end_id = _nid(), _nid()
    t_nodes = [{"node_id": start_id, "node_type": "start", "label": "开始", "actor_roles": [],
                "source_turn_ids": [], "confidence": 1.0, "expert_confirmed": False}]
    tasks = []
    for i, item in enumerate(items):
        task_id = _nid()
        t_nodes.append({"node_id": task_id, "node_type": "activity", "label": item["name"],
                        "actor_roles": [item["owner"]] if item.get("owner") else [],
                        "source_turn_ids": [], "confidence": confidence, "expert_confirmed": False})
        tasks.append({"task_id": task_id, "sop_node_ids": sop_ids[i],
                      "definition_source": "expert_defined", "structured_by": structured_by})
    t_nodes.append({"node_id": end_id, "node_type": "end", "label": "结束", "actor_roles": [],
                    "source_turn_ids": [], "confidence": 1.0, "expert_confirmed": False})

    chain = [start_id] + [t["task_id"] for t in tasks] + [end_id]
    t_edges = []
    for i in range(len(chain) - 1):
        edge_type = "normal"
        # A change of responsible party between two consecutive tasks is exactly what a
        # handoff edge means -- but only when the expert actually named both owners.
        if 0 < i < len(chain) - 2:
            a, b = items[i - 1].get("owner"), items[i].get("owner")
            if a and b and a != b:
                edge_type = "handoff"
        t_edges.append({"edge_id": _nid(), "from": chain[i], "to": chain[i + 1], "edge_type": edge_type,
                        "confidence": confidence, "expert_confirmed": False, "source_turn_ids": []})

    return {
        "graph": {"graph_type": "dag", "start_node_ids": [start_id], "end_node_ids": [end_id],
                  "nodes": t_nodes, "edges": t_edges},
        "tasks": tasks,
    }
