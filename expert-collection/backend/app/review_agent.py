"""Review loop engine (IMPLEMENTATION_PLAN.md section 17) -- one conversation engine for
creating a workflow from a narration, editing it, and annotating / arbitrating a record.

The loop, whatever the mode:
    person says something -> (first time in "create": narrative -> draft graph) ->
    agent restates what it understood, lists the concrete graph changes it made, asks the
    next clarification question -> ... -> person is satisfied -> agent reads the whole
    graph back (and, when annotating, proposes a verdict) -> person confirms -> done.

Division of labour (same principle as section 15): the model interprets language -- what the
person meant, which graph edits that implies, how to phrase a question -- while everything
that decides what gets saved is checked here in code:
- graph edits use graph_ops' change protocol and are applied to a copy first; if they
  introduce new graph_validator errors, none of them are applied and the person is told so;
- a new step's evidence quote must actually occur in what the person said, otherwise the
  step is kept but flagged as unverified (and asked about first) -- never silently trusted;
- questions must come from the clarification list (review_gaps) the code offered;
- the final read-back is generated from the graph itself, not by the model, so what the
  person confirms is exactly what gets saved.

State (persisted by the caller -- on a workflow record as `_review`, on an annotation session
as `review`):
    {mode, phase, gaps, questions_asked, max_questions, pending_gap_id, snapshots,
     base_graph (annotate/arbitrate), proposal (annotate/arbitrate), candidates (arbitrate)}
phase: "narrative" (create only, before the first draft) -> "review" -> "final_confirm" -> "done".
"""
from __future__ import annotations

import copy
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from . import gold_annotation, graph_ops, graph_validator, guide_service, llm_client, review_gaps
from . import settings as app_settings

EXTRACT_SLOT = "graph_regenerate"   # C_standard by default
REVIEW_SLOT = "guide_service"       # C_standard by default since section 17
EXTRACT_TIMEOUT = 90.0
REVIEW_TIMEOUT = 60.0
MIN_NARRATIVE_CHARS = 60
MAX_SNAPSHOTS = 30

REASON_TAGS = ["missing_step", "extra_step", "wrong_order", "duplicate", "wrong_branch",
               "wrong_role", "unclear_label", "out_of_scope", "other"]
REASON_LABELS = {
    "missing_step": "步骤缺失", "extra_step": "多余步骤", "wrong_order": "顺序错误", "duplicate": "重复",
    "wrong_branch": "分支/条件错误", "wrong_role": "角色错误", "unclear_label": "描述不清",
    "out_of_scope": "不属于该场景", "other": "其他",
}
VERDICT_LABELS = {"accepted": "采纳", "needs_revision": "需要修改", "rejected": "丢弃"}
_JARGON = ("分支", "并行", "汇合", "节点", "DAG", "dag")

SAMPLE_NARRATION = (
    "上周三夜班，3 号加工中心突然报警，尺寸超差。操作员先按急停，把这批零件隔离到待判区，"
    "然后打电话叫质量工程师。质量工程师到了先复测：如果复测正常，就解除隔离、恢复生产；"
    "如果确认超差，设备工程师查主轴和夹具，工艺员同时查刀具磨损和程序参数，两边查完一起碰结果。"
    "换刀或调参数之后要试切首件，首件由质检签字确认，不合格就回到查原因那一步重来。"
    "首件合格、班组长签字放行，这件事就算处理完了。最难的是判断是刀具还是夹具的问题，主要靠听声音和看切屑。"
)

INTRO_TEXT = (
    "请您把这件事完整地讲一遍，打字或点麦克风说都可以，想到哪说到哪，不用在意格式。"
    "讲的时候尽量带上这些：什么情况下开始的；按顺序谁做了什么；遇到什么情况会走不同的处理；"
    "哪些事是同时做的；哪一步要等谁签字或确认；什么情况要回头重做；做到哪一步算结束；哪里最靠经验。"
    "讲完之后我会整理成流程图，再就不清楚的地方跟您确认。"
)


# --- small helpers -------------------------------------------------------------------------

def _slot(slot: str) -> dict:
    return app_settings.resolve_slot_for_call(app_settings.get_effective_settings(), slot)


def _usable(cfg: dict) -> bool:
    return bool(cfg.get("enabled") and cfg.get("endpoint") and cfg.get("model_name"))


def available() -> bool:
    """Whether a new workflow should use the review loop (both model slots reachable). When
    not, the caller falls back to section 15's step-by-step guide."""
    return _usable(_slot(EXTRACT_SLOT)) and _usable(_slot(REVIEW_SLOT))


def max_questions() -> int:
    value = (app_settings.get_effective_settings().get("review") or {}).get("max_clarify_questions", 20)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 20


_PUNCT = re.compile(r"[\s，。、；：！？,.;:!?\"“”'‘’（）()《》<>【】\[\]—\-…·]+")


def _norm(text: str) -> str:
    return _PUNCT.sub("", text or "")


def quote_found(quote: str, sources: list[str]) -> bool:
    q = _norm(quote)
    return len(q) >= 2 and any(q in _norm(s) for s in sources)


def _is_short(text: str, limit: int) -> bool:
    return len(_norm(text)) <= limit


_AFFIRM = re.compile(r"^(确认|确定|是|是的|对|对的|没错|没问题|可以|好|好的|行|提交|同意|就这样|ok|OK|嗯|嗯嗯)(了|吧|的|啊|呀)?$")
_SATISFIED = re.compile(r"(没问题|都对|可以了|满意|没有要改|不用改|就这样吧?|挺好)")
_REJECT = re.compile(r"(丢弃|不能用|没法用|用不了|作废|不要这条)")
_UNDO = re.compile(r"(撤销|撤回|退回上一步|恢复到上一步|刚才的?改动不要)")


def rule_intent(text: str, *, phase: str, mode: str, question_pending: bool = False) -> str | None:
    """Cheap, reliable intents for short replies -- checked before (and without) the model.
    A bare "对/是" while a clarification question is pending is an *answer* to that question,
    not "I'm satisfied", so it goes to the model instead."""
    t = (text or "").strip()
    if _is_short(t, 12) and _UNDO.search(t):
        return "undo"
    if phase == "final_confirm" and _AFFIRM.match(_norm(t)):
        return "confirm"
    if mode in ("annotate", "arbitrate") and _is_short(t, 12) and _REJECT.search(t):
        return "reject"
    if _is_short(t, 10) and (_SATISFIED.search(t) or (not question_pending and _AFFIRM.match(_norm(t)))):
        return "satisfied"
    return None


# --- read-back and change descriptions (deterministic) -------------------------------------

def _topo_order(graph: dict) -> list[dict]:
    nodes = graph.get("nodes", [])
    indeg = {n["node_id"]: 0 for n in nodes}
    for e in graph.get("edges", []):
        if e["to"] in indeg:
            indeg[e["to"]] += 1
    order, ready = [], [n for n in nodes if indeg[n["node_id"]] == 0]
    seen = set()
    while ready:
        n = ready.pop(0)
        if n["node_id"] in seen:
            continue
        seen.add(n["node_id"])
        order.append(n)
        for e in graph.get("edges", []):
            if e["from"] == n["node_id"] and e["to"] in indeg:
                indeg[e["to"]] -= 1
                if indeg[e["to"]] == 0:
                    ready.append(next(x for x in nodes if x["node_id"] == e["to"]))
    order += [n for n in nodes if n["node_id"] not in seen]  # cycles: still list them
    return order


def readback(graph: dict) -> str:
    """The whole graph as numbered plain-language lines -- generated from the graph itself so
    what the person confirms is exactly what gets saved."""
    by_id = {n["node_id"]: n for n in graph.get("nodes", [])}
    lines = []
    for i, n in enumerate(_topo_order(graph), 1):
        actors = f"（{'、'.join(n['actor_roles'])}）" if n.get("actor_roles") else ""
        text = f"{i}. {n['label']}{actors}"
        outs = [e for e in graph.get("edges", []) if e["from"] == n["node_id"]]
        if n["node_type"] == "decision" and outs:
            parts = [f"{e.get('condition') or '（条件未说明）'} → {by_id.get(e['to'], {}).get('label', e['to'])}" for e in outs]
            text += "：" + "；".join(parts)
        elif n["node_type"] == "parallel_split" and outs:
            text += "，同时进行：" + "、".join(by_id.get(e["to"], {}).get("label", e["to"]) for e in outs)
        elif n["node_type"] == "approval":
            text += "（需要签字/确认）"
        retry = n.get("retry_semantics") or {}
        if retry.get("enabled"):
            target = by_id.get(retry.get("rework_reference_node_id") or "", {}).get("label")
            text += f"；{retry.get('condition') or '不合格'}时回到「{target}」重做" if target else "；可能需要返工"
        lines.append(text)
    return "\n".join(lines)


def describe_changes(before: dict, after: dict) -> tuple[list[str], set[str]]:
    """Plain-language list of what changed between two graphs, plus the reason-tag categories
    those changes suggest (used when the model gives no tags)."""
    b_nodes = {n["node_id"]: n for n in before.get("nodes", [])}
    a_nodes = {n["node_id"]: n for n in after.get("nodes", [])}
    out: list[str] = []
    cats: set[str] = set()
    removed = [b_nodes[i] for i in b_nodes if i not in a_nodes]
    added = [a_nodes[i] for i in a_nodes if i not in b_nodes]
    survivors_text = " ".join(n["label"] for n in a_nodes.values())
    for n in added:
        out.append(f"新增步骤「{n['label']}」")
        cats.add("missing_step" if n["node_type"] != "decision" else "wrong_branch")
    for n in removed:
        if n["label"] and n["label"] in survivors_text:
            out.append(f"把「{n['label']}」合并到了别的步骤里")
            cats.add("duplicate")
        else:
            out.append(f"删除步骤「{n['label']}」")
            cats.add("extra_step")
    for i, a in a_nodes.items():
        b = b_nodes.get(i)
        if not b:
            continue
        if a["label"] != b["label"]:
            out.append(f"「{b['label']}」改为「{a['label']}」")
            cats.add("unclear_label")
        if sorted(a.get("actor_roles") or []) != sorted(b.get("actor_roles") or []):
            who = "、".join(a.get("actor_roles") or []) or "（未指定）"
            out.append(f"「{a['label']}」由 {who} 负责")
            cats.add("wrong_role")
        if a["node_type"] != b["node_type"]:
            out.append(f"「{a['label']}」的类型调整了")
            cats.add("wrong_branch" if "decision" in (a["node_type"], b["node_type"]) else "wrong_order")
        if (a.get("retry_semantics") or {}) != (b.get("retry_semantics") or {}):
            out.append(f"「{a['label']}」补充了返工说明")
            cats.add("wrong_order")

    def edge_key(e, nodes):
        return (nodes.get(e["from"], {}).get("label", e["from"]), nodes.get(e["to"], {}).get("label", e["to"]))

    b_edges = {edge_key(e, b_nodes): e for e in before.get("edges", [])}
    a_edges = {edge_key(e, a_nodes): e for e in after.get("edges", [])}
    touched = {n["label"] for n in added + removed}
    for k, e in a_edges.items():
        if k not in b_edges:
            if k[0] not in touched and k[1] not in touched:
                out.append(f"「{k[0]}」之后改为接「{k[1]}」")
                cats.add("wrong_order")
        elif (e.get("condition") or "") != (b_edges[k].get("condition") or ""):
            out.append(f"「{k[0]}」→「{k[1]}」的条件改为「{e.get('condition') or '无'}」")
            cats.add("wrong_branch")
    for k in b_edges:
        if k not in a_edges and k[0] not in touched and k[1] not in touched and k[0] in {n['label'] for n in a_nodes.values()}:
            out.append(f"去掉了「{k[0]}」→「{k[1]}」")
            cats.add("wrong_order")
    return out, cats


# --- model calls ----------------------------------------------------------------------------

_EXTRACT_PROMPT = """你是制造业专家访谈助手的流程整理模块。下面是专家对一件事的完整讲述（可能分几段）。请把它整理成一张流程图（有向无环图）。

严格规则：
- 只使用专家明确说过的内容，不编造步骤、分支或执行人。
- 每个节点的 label 用专家的措辞提炼成短语；每个非 start/end 节点必须给 "evidence"：从专家原话中**原样摘抄**的一小段（能证明这一步存在），不能改写。
- 返工/重试用节点的 retry_semantics 表达，不要建指回前面的边；图必须无环，有 start 和 end。
- 判断节点（decision）的每条出边用 conditional 类型并写清 condition；同时进行用 parallel_split/parallel_join。
- 对讲述里含糊、没说清楚的地方，放进 uncertainties，写成一个口语化的问题（不要用"分支/并行/节点"这类术语）。

只输出一个 JSON object：
{"nodes":[{"node_id":"n1","node_type":"start|activity|decision|parallel_split|parallel_join|merge|approval|handoff|wait|end","label":"...","actor_roles":["..."],"decision_question":null,"evidence":"原话摘抄","retry_semantics":null 或 {"enabled":true,"rework_reference_node_id":"nX","condition":"...","description":"..."}}],
 "edges":[{"edge_id":"e1","from":"n1","to":"n2","edge_type":"normal|conditional|parallel|merge|handoff|approval|timeout|exception_forward","condition":null}],
 "start_node_ids":["n1"],"end_node_ids":["nK"],
 "summary":"用两三句话复述你理解的整个过程（第二人称“您”，不加评价）",
 "uncertainties":[{"question":"...","node_ids":["nX"]}],
 "case_context":{"scenario_trigger":"起因或null","scenario_goal":"目标或null","constraints":"限制条件或null"}}
只输出 JSON。"""


def extract_from_narrative(narrative_texts: list[str], turn_id: str) -> dict:
    """Narrative -> {graph, summary, gaps(model), case_context}. Raises llm_client.LLMError."""
    cfg = _slot(EXTRACT_SLOT)
    if not _usable(cfg):
        raise llm_client.LLMError("not_configured", "「整理流程图」环节未配置可用的模型（系统管理 → 模型配置）")
    narrative = "\n\n".join(narrative_texts)
    parsed = llm_client.chat_completion_json(cfg, [
        {"role": "system", "content": _EXTRACT_PROMPT},
        {"role": "user", "content": narrative},
    ], timeout=EXTRACT_TIMEOUT)
    graph = guide_service._coerce_regenerated_graph(parsed)
    if graph is None:
        raise llm_client.LLMError("bad_response", "模型整理出的流程图格式不符合要求")
    raw_nodes = {n.get("node_id"): n for n in parsed.get("nodes", []) if isinstance(n, dict)}
    by_id = {n["node_id"] for n in graph["nodes"]}
    for n in graph["nodes"]:
        raw = raw_nodes.get(n["node_id"], {})
        quote = raw.get("evidence")
        n["evidence"] = [quote.strip()] if isinstance(quote, str) and quote_found(quote, narrative_texts) else []
        n["source_turn_ids"] = [turn_id]
        retry = raw.get("retry_semantics")
        if isinstance(retry, dict) and retry.get("enabled"):
            ref = retry.get("rework_reference_node_id")
            n["retry_semantics"] = {
                "enabled": True,
                "rework_reference_node_id": ref if ref in by_id else None,
                "condition": retry.get("condition") if isinstance(retry.get("condition"), str) else None,
                "description": retry.get("description") if isinstance(retry.get("description"), str) else None,
            }
    for e in graph["edges"]:
        e["source_turn_ids"] = [turn_id]
    gaps = []
    for u in parsed.get("uncertainties") or []:
        if isinstance(u, dict) and isinstance(u.get("question"), str) and u["question"].strip():
            ids = [i for i in (u.get("node_ids") or []) if i in by_id]
            gaps.append(review_gaps.model_gap(u["question"].strip()[:150], ids))
    cc = parsed.get("case_context") if isinstance(parsed.get("case_context"), dict) else {}
    case_context = {k: v.strip() for k, v in cc.items()
                    if k in ("scenario_trigger", "scenario_goal", "constraints") and isinstance(v, str) and v.strip()}
    summary = parsed.get("summary") if isinstance(parsed.get("summary"), str) else ""
    return {"graph": graph, "summary": summary.strip()[:400], "gaps": gaps[:6], "case_context": case_context}


_REVIEW_PROMPT = """你是制造业流程审阅助手。你面前有一张流程图，对方（{who}）正在和你对话，目的是把这张图改到完全符合实际。

你要做的：
1. 理解对方这句话：是在纠正/补充（intent=edit）、回答你刚才的问题（intent=answer）、表示满意没什么要改了（intent=satisfied）{reject_line}{adopt_line}，还是别的（intent=other）。
2. 如果需要改图，给出 ops（修改操作），只能用下面这些：
   {{"op":"add_node","node":{{"node_id":"新id","node_type":"activity|decision|approval|handoff|wait|parallel_split|parallel_join|merge|start|end","label":"短语","actor_roles":[],"decision_question":null}}}}
   {{"op":"update_node","node_id":"已有id","patch":{{"label":"...","actor_roles":[...],"node_type":"...","decision_question":"..."}}}}
   {{"op":"remove_node","node_id":"已有id"}}
   {{"op":"add_edge","edge":{{"edge_id":"新id","from":"id","to":"id","edge_type":"normal|conditional|parallel|merge|handoff|approval","condition":null}}}}
   {{"op":"update_edge","edge_id":"已有id","patch":{{"from":"id","to":"id","edge_type":"...","condition":"..."}}}}
   {{"op":"remove_edge","edge_id":"已有id"}}
   {{"op":"set_retry_semantics","node_id":"id","retry_semantics":{{"enabled":true,"rework_reference_node_id":"id","condition":"...","description":"..."}}}}
   删掉一个中间步骤时，记得把它前后的步骤连起来；插入步骤时，改接原来的连线。图必须保持无环。
   每个新增节点，在 evidence 里给出对方原话中能证明它的**原样摘抄**。
3. understanding：用一句话复述你理解的对方意思（“您是说……”），不评价，不编造。
4. resolved_gap_ids：对方这句话已经说清楚了下面清单里的哪些项。
5. question：如果还有需要问的，从下面的待澄清清单里选**一项**，用口语问出来（一个问题，不用"分支/并行/节点"这类术语）；清单为空或对方表示满意就给 null。
6. new_uncertainties：对方的话里又出现了哪些没说清楚、需要以后确认的点（最多 2 个，写成问题）。{tags_line}

只输出一个 JSON object：{{"intent":"...","understanding":"...","ops":[...],"evidence":{{"新节点id":"原话摘抄"}},"resolved_gap_ids":[...],"question":{{"gap_id":"...","text":"..."}}或null,"new_uncertainties":[{{"question":"...","node_ids":[]}}]{tags_field}{adopt_field}}}"""


def _graph_for_prompt(graph: dict) -> str:
    return json.dumps({
        "nodes": [{k: n.get(k) for k in ("node_id", "node_type", "label", "actor_roles", "decision_question")} |
                  ({"retry_semantics": n["retry_semantics"]} if n.get("retry_semantics") else {})
                  for n in graph.get("nodes", [])],
        "edges": [{k: e.get(k) for k in ("edge_id", "from", "to", "edge_type", "condition")} for e in graph.get("edges", [])],
    }, ensure_ascii=False)


def _call_review_model(state: dict, graph: dict, turns: list[dict], text: str, offered: list[dict]) -> dict:
    cfg = _slot(REVIEW_SLOT)
    if not _usable(cfg):
        raise llm_client.LLMError("not_configured", "审阅对话环节未配置可用的模型（系统管理 → 模型配置）")
    mode = state["mode"]
    annotating = mode in ("annotate", "arbitrate")
    system = _REVIEW_PROMPT.format(
        who="标注人" if annotating else "讲述这个流程的专家",
        reject_line="、认为这条流程根本不能用（intent=reject）" if annotating else "",
        adopt_line="、要求直接采用某位标注人的版本（intent=adopt，并给 adopt_annotation_id）" if mode == "arbitrate" else "",
        tags_line=("\n7. reason_tags：如果图被改过或对方认为不能用，从这些里选问题类型：" + "、".join(
            f"{k}={v}" for k, v in REASON_LABELS.items() if k != "other")) if annotating else "",
        tags_field=',"reason_tags":[...]' if annotating else "",
        adopt_field=',"adopt_annotation_id":null' if mode == "arbitrate" else "",
    )
    context = {
        "当前流程图": json.loads(_graph_for_prompt(graph)),
        "待澄清清单": [{"gap_id": g["id"], "问题": g["text"]} for g in offered],
        "你上一轮问的": next((g["text"] for g in state.get("gaps", []) if g["id"] == state.get("pending_gap_id")), None),
    }
    if mode == "arbitrate":
        context["两位标注人的结果"] = [
            {"annotation_id": c["annotation_id"], "标注人": c["annotator_name"], "结论": VERDICT_LABELS.get(c["verdict"], c["verdict"]),
             "改动": c.get("changes", [])} for c in state.get("candidates", [])
        ]
    recent = [f"{'对方' if t['role'] == 'expert' else '助手'}：{t['text']}" for t in turns[-12:]]
    user = (f"背景（JSON）：{json.dumps(context, ensure_ascii=False)}\n\n最近的对话：\n" + "\n".join(recent) +
            f"\n\n对方刚说：{text}")
    return llm_client.chat_completion_json(cfg, [
        {"role": "system", "content": system}, {"role": "user", "content": user},
    ], timeout=REVIEW_TIMEOUT)


_NODE_TYPES = guide_service._VALID_NODE_TYPES
_EDGE_TYPES = guide_service._VALID_EDGE_TYPES


def sanitize_ops(raw_ops: Any, graph: dict, evidence: dict, sources: list[str], turn_id: str) -> tuple[list[dict], list[str]]:
    """Model ops -> graph_ops ops with only known fields, fresh ids for anything new, and the
    evidence rule applied. Returns (ops, unverified_new_node_ids). Malformed ops are dropped."""
    node_ids = {n["node_id"] for n in graph.get("nodes", [])}
    edge_ids = {e["edge_id"] for e in graph.get("edges", [])}
    id_map: dict[str, str] = {}
    ops: list[dict] = []
    unverified: list[str] = []

    def fresh(prefix: str, taken: set[str]) -> str:
        while True:
            nid = f"{prefix}{uuid.uuid4().hex[:6]}"
            if nid not in taken:
                taken.add(nid)
                return nid

    def ref(x: Any) -> str | None:
        if not isinstance(x, str):
            return None
        return id_map.get(x, x if x in node_ids else None)

    for op in raw_ops if isinstance(raw_ops, list) else []:
        if not isinstance(op, dict):
            continue
        kind = op.get("op")
        if kind == "add_node" and isinstance(op.get("node"), dict):
            n = op["node"]
            label = n.get("label")
            if not isinstance(label, str) or not label.strip() or n.get("node_type") not in _NODE_TYPES:
                continue
            new_id = fresh("n", node_ids)
            if isinstance(n.get("node_id"), str):
                id_map[n["node_id"]] = new_id
            quote = evidence.get(n.get("node_id")) if isinstance(evidence, dict) else None
            ok = isinstance(quote, str) and quote_found(quote, sources)
            if not ok and n["node_type"] not in ("start", "end"):
                unverified.append(new_id)
            ops.append({"op": "add_node", "node": {
                "node_id": new_id, "node_type": n["node_type"], "label": label.strip()[:120],
                "actor_roles": [r for r in (n.get("actor_roles") or []) if isinstance(r, str) and r.strip()],
                "decision_question": n.get("decision_question") if isinstance(n.get("decision_question"), str) else None,
                "confidence": 0.8, "expert_confirmed": False, "source_turn_ids": [turn_id],
                "evidence": [quote.strip()] if ok else [],
            }})
            if n["node_type"] == "start":
                ops.append({"op": "set_start", "node_id": new_id})
            if n["node_type"] == "end":
                ops.append({"op": "set_end", "node_id": new_id})
        elif kind == "update_node" and ref(op.get("node_id")) and isinstance(op.get("patch"), dict):
            patch = {}
            p = op["patch"]
            if isinstance(p.get("label"), str) and p["label"].strip():
                patch["label"] = p["label"].strip()[:120]
            if isinstance(p.get("actor_roles"), list):
                patch["actor_roles"] = [r for r in p["actor_roles"] if isinstance(r, str) and r.strip()]
            if p.get("node_type") in _NODE_TYPES:
                patch["node_type"] = p["node_type"]
            if isinstance(p.get("decision_question"), str):
                patch["decision_question"] = p["decision_question"]
            if patch:
                ops.append({"op": "update_node", "node_id": ref(op["node_id"]), "patch": patch})
        elif kind == "remove_node" and ref(op.get("node_id")):
            ops.append({"op": "remove_node", "node_id": ref(op["node_id"])})
        elif kind == "add_edge" and isinstance(op.get("edge"), dict):
            e = op["edge"]
            src, dst = ref(e.get("from")), ref(e.get("to"))
            if not src or not dst or src == dst or e.get("edge_type") not in _EDGE_TYPES:
                continue
            ops.append({"op": "add_edge", "edge": {
                "edge_id": fresh("e", edge_ids), "from": src, "to": dst, "edge_type": e["edge_type"],
                "condition": e.get("condition") if isinstance(e.get("condition"), str) and e["condition"].strip() else None,
                "confidence": 0.8, "expert_confirmed": False, "source_turn_ids": [turn_id],
            }})
        elif kind == "update_edge" and op.get("edge_id") in edge_ids and isinstance(op.get("patch"), dict):
            p, patch = op["patch"], {}
            for key in ("from", "to"):
                if key in p and ref(p[key]):
                    patch[key] = ref(p[key])
            if p.get("edge_type") in _EDGE_TYPES:
                patch["edge_type"] = p["edge_type"]
            if "condition" in p and (p["condition"] is None or isinstance(p["condition"], str)):
                patch["condition"] = p["condition"]
            if patch:
                ops.append({"op": "update_edge", "edge_id": op["edge_id"], "patch": patch})
        elif kind == "remove_edge" and op.get("edge_id") in edge_ids:
            ops.append({"op": "remove_edge", "edge_id": op["edge_id"]})
        elif kind == "set_retry_semantics" and ref(op.get("node_id")) and isinstance(op.get("retry_semantics"), dict):
            r = op["retry_semantics"]
            ops.append({"op": "set_retry_semantics", "node_id": ref(op["node_id"]), "retry_semantics": {
                "enabled": bool(r.get("enabled", True)),
                "rework_reference_node_id": ref(r.get("rework_reference_node_id")),
                "condition": r.get("condition") if isinstance(r.get("condition"), str) else None,
                "description": r.get("description") if isinstance(r.get("description"), str) else None,
            }})
    return ops, unverified


def _error_keys(graph: dict) -> set[tuple]:
    return {(i["code"], i.get("node_id"), i.get("edge_id")) for i in graph_validator.validate(graph) if i["level"] == "error"}


def _valid_question(q: Any, offered_ids: set[str]) -> tuple[str, str] | None:
    if not isinstance(q, dict) or q.get("gap_id") not in offered_ids:
        return None
    text = q.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > 160 or any(j in text for j in _JARGON):
        return q["gap_id"], ""
    return q["gap_id"], text.strip()


# --- the turn -------------------------------------------------------------------------------

@dataclass
class TurnResult:
    ack: str | None = None                     # restatement of what the person said
    changes: list[str] = field(default_factory=list)
    body: str | None = None                    # read-back / notices (multi-line)
    question: str | None = None
    graph: dict | None = None                  # new graph (None = unchanged)
    state: dict | None = None
    finished: bool = False                     # person confirmed -> caller commits
    case_context: dict | None = None

    @property
    def text(self) -> str:
        parts = [self.ack or "", "；".join(self.changes) and "图上的改动：" + "；".join(self.changes), self.body or "", self.question or ""]
        return "\n".join(p for p in parts if p)


def new_state(mode: str, *, base_graph: dict | None = None, candidates: list[dict] | None = None) -> dict:
    return {
        "mode": mode, "phase": "narrative" if mode == "create" else "review",
        "gaps": [], "questions_asked": 0, "max_questions": max_questions(),
        "pending_gap_id": None, "snapshots": [], "base_graph": base_graph,
        "proposal": None, "candidates": candidates or [],
    }


def opening(state: dict, graph: dict) -> TurnResult:
    """The agent's first message for a new review session."""
    mode = state["mode"]
    state = copy.deepcopy(state)
    if mode == "create":
        return TurnResult(body=INTRO_TEXT, state=state)
    if mode == "edit":
        state["gaps"] = review_gaps.refresh([], graph, mode=mode)
        return TurnResult(body="这是目前的流程：\n" + readback(graph), question="想改哪里直接告诉我；没问题的话说「没问题」。", state=state)
    state["gaps"] = review_gaps.refresh([], graph, mode=mode)
    if mode == "annotate":
        state["phase"] = "final_confirm"
        state["proposal"] = {"verdict": "accepted", "reason_tags": []}
        return TurnResult(
            body="这是待审的流程：\n" + readback(graph),
            question="有不对、缺漏或多余的地方直接说，我来改；都对的话回复「确认」，结论就是「采纳」。说「这条不能用」则结论为「丢弃」。",
            state=state)
    lines = ["两位标注人的结论不一致（或修改不同），需要您来仲裁。待审的原始流程：", readback(graph), ""]
    for c in state.get("candidates", []):
        lines.append(f"· {c['annotator_name']}：{VERDICT_LABELS.get(c['verdict'], c['verdict'])}"
                     + (f"（原因：{'、'.join(REASON_LABELS.get(t, t) for t in c.get('reason_tags', []))}）" if c.get("reason_tags") else "")
                     + (f"；改动：{'；'.join(c.get('changes', [])[:8])}" if c.get("changes") else ""))
    return TurnResult(body="\n".join(lines),
                      question="您可以说「用某某的版本」、在某一份上继续改、采纳原图，或说「这条不能用」。",
                      state=state)


def _snapshot(state: dict, graph: dict, turn_id: str) -> None:
    state["snapshots"] = (state.get("snapshots") or [])[-(MAX_SNAPSHOTS - 1):] + [{
        "turn_id": turn_id, "graph": copy.deepcopy(graph), "gaps": copy.deepcopy(state.get("gaps", [])),
        "phase": state["phase"], "questions_asked": state.get("questions_asked", 0),
        "pending_gap_id": state.get("pending_gap_id"), "proposal": copy.deepcopy(state.get("proposal")),
    }]


def propose_verdict(state: dict, graph: dict, *, rejected: bool, model_tags: list[str] | None = None) -> dict:
    base = state.get("base_graph") or graph
    if rejected:
        tags = [t for t in (model_tags or []) if t in REASON_TAGS and t != "other"] or ["out_of_scope"]
        return {"verdict": "rejected", "reason_tags": tags}
    if gold_annotation.graph_signature(base) == gold_annotation.graph_signature(graph):
        return {"verdict": "accepted", "reason_tags": []}
    _, cats = describe_changes(base, graph)
    tags = [t for t in (model_tags or []) if t in REASON_TAGS and t != "other"] or sorted(cats) or ["unclear_label"]
    return {"verdict": "needs_revision", "reason_tags": tags}


def _final_confirm(state: dict, graph: dict, result: TurnResult, *, rejected: bool = False, model_tags=None) -> TurnResult:
    state["phase"] = "final_confirm"
    state["pending_gap_id"] = None
    if state["mode"] in ("annotate", "arbitrate"):
        state["proposal"] = propose_verdict(state, graph, rejected=rejected, model_tags=model_tags)
        v = state["proposal"]
        why = f"（原因：{'、'.join(REASON_LABELS[t] for t in v['reason_tags'])}）" if v["reason_tags"] else ""
        if v["verdict"] == "rejected":
            result.body = f"我的标注结论：丢弃{why}。"
        else:
            result.body = f"修改后的完整流程：\n{readback(graph)}\n\n我的标注结论：{VERDICT_LABELS[v['verdict']]}{why}。"
        result.question = "没问题的话回复「确认」提交标注；要改结论或流程，直接告诉我。"
    else:
        result.body = "我整理的完整流程是：\n" + readback(graph)
        result.question = "这样对吗？没问题的话回复「确认」就提交；要改的话直接告诉我。"
    return result


def _next_question(state: dict, graph: dict, result: TurnResult, preferred: tuple[str, str] | None) -> TurnResult:
    open_ = review_gaps.open_gaps(state["gaps"])
    if open_ and state["questions_asked"] < state["max_questions"]:
        chosen = next((g for g in open_ if preferred and g["id"] == preferred[0]), open_[0])
        text = preferred[1] if preferred and preferred[0] == chosen["id"] and preferred[1] else chosen["text"]
        state["gaps"] = review_gaps.mark(state["gaps"], [chosen["id"]], "asked")
        state["questions_asked"] += 1
        state["pending_gap_id"] = chosen["id"]
        state["phase"] = "review"
        result.question = text
        return result
    return _final_confirm(state, graph, result)


def handle_turn(state: dict, graph: dict, turns: list[dict], text: str, turn_id: str) -> TurnResult:
    """One person message -> agent reply. `turns` is the transcript *including* this message.
    Never raises for model failures: they come back as an honest notice with nothing changed."""
    state = copy.deepcopy(state)
    mode, phase = state["mode"], state["phase"]
    person_texts = [t["text"] for t in turns if t["role"] == "expert"]

    # 1. Narrative (create, before the first draft).
    if phase == "narrative":
        narrative = person_texts
        if len(_norm("".join(narrative))) < MIN_NARRATIVE_CHARS:
            return TurnResult(body="能再多讲一些吗？把这件事从开始到结束的经过完整讲一遍，谁先做什么、后做什么、遇到什么情况怎么处理。"
                                   "想到哪说到哪就好，我整理好之后再跟您确认细节。", state=state)
        try:
            extracted = extract_from_narrative(narrative, turn_id)
        except llm_client.LLMError as e:
            return TurnResult(body=f"整理流程图时 AI 服务出错（{e}）。您讲的内容已经保存，稍后发一句「重试」我再整理一次。", state=state)
        new_graph = extracted["graph"]
        state["phase"] = "review"
        state["gaps"] = review_gaps.refresh([], new_graph, mode=mode, new_model_gaps=extracted["gaps"])
        result = TurnResult(ack=extracted["summary"] or None,
                            changes=[f"根据您的讲述整理出 {sum(1 for n in new_graph['nodes'] if n['node_type'] not in ('start', 'end'))} 个步骤"],
                            graph=new_graph, state=state, case_context=extracted["case_context"])
        return _next_question(state, new_graph, result, None)

    # 2. Rule intents for short replies (no model needed).
    intent = rule_intent(text, phase=phase, mode=mode, question_pending=bool(state.get("pending_gap_id")))
    if intent == "undo":
        snaps = state.get("snapshots") or []
        if not snaps:
            return TurnResult(body="现在没有可以撤销的修改。", state=state)
        last = snaps.pop()
        state.update({"snapshots": snaps, "gaps": last["gaps"], "phase": last["phase"], "questions_asked": last["questions_asked"],
                      "pending_gap_id": last["pending_gap_id"], "proposal": last.get("proposal")})
        return TurnResult(body="已撤销上一轮的修改，流程图恢复到之前的样子。", graph=last["graph"], state=state)
    if intent == "confirm":
        if any(i["level"] == "error" for i in graph_validator.validate(graph)):
            state["gaps"] = review_gaps.refresh(state["gaps"], graph, mode=mode)
            result = TurnResult(body="流程图还有结构上的问题，暂时不能提交。", state=state)
            return _next_question(state, graph, result, None)
        state["phase"] = "done"
        return TurnResult(body="好的，已确认。", state=state, finished=True)
    if intent in ("satisfied", "reject"):
        return _final_confirm(state, graph, TurnResult(state=state), rejected=intent == "reject")

    # 3. Model turn.
    offered = review_gaps.open_gaps(state["gaps"])[:5]
    try:
        out = _call_review_model(state, graph, turns, text, offered)
    except llm_client.LLMError as e:
        if e.kind == "not_configured":
            return TurnResult(body="当前没有配置可用的 AI 模型，只能处理「没问题 / 确认 / 撤销" +
                                   (" / 这条不能用" if mode in ("annotate", "arbitrate") else "") + "」，没法按您的描述改图。", state=state)
        return TurnResult(body=f"AI 服务暂时出错（{e}），这句话没有处理，图也没有改动。请稍后再发一次。", state=state)

    intent = out.get("intent") if out.get("intent") in ("edit", "answer", "satisfied", "reject", "adopt", "other") else "other"
    understanding = out.get("understanding") if isinstance(out.get("understanding"), str) else None
    model_tags = [t for t in (out.get("reason_tags") or []) if isinstance(t, str)]
    result = TurnResult(ack=(understanding or "").strip()[:200] or None, state=state)
    _snapshot(state, graph, turn_id)

    new_graph = graph
    if intent == "adopt" and mode == "arbitrate":
        cand = next((c for c in state.get("candidates", []) if c["annotation_id"] == out.get("adopt_annotation_id")), None)
        if cand and cand.get("revised_graph"):
            new_graph = copy.deepcopy(cand["revised_graph"])
            result.changes = [f"采用了 {cand['annotator_name']} 修改后的版本"]
        elif cand:
            new_graph = copy.deepcopy(state.get("base_graph") or graph)
            result.changes = [f"按 {cand['annotator_name']} 的结论，使用原始流程"]
    else:
        ops, unverified = sanitize_ops(out.get("ops"), graph, out.get("evidence") or {}, [text] + person_texts, turn_id)
        if ops:
            candidate = graph_ops.apply_ops(copy.deepcopy(graph), ops)
            introduced = _error_keys(candidate) - _error_keys(graph)
            if introduced:
                msgs = {i["message"] for i in graph_validator.validate(candidate) if (i["code"], i.get("node_id"), i.get("edge_id")) in introduced}
                result.body = "这次的修改会让流程图出问题（" + "；".join(sorted(msgs))[:200] + "），我没有改图。能换个说法再说一下吗？"
                state["snapshots"].pop()
                return result
            new_graph = candidate
            result.changes, _ = describe_changes(graph, new_graph)
            for nid in unverified:
                label = next((n["label"] for n in new_graph["nodes"] if n["node_id"] == nid), nid)
                state["gaps"].append(review_gaps.model_gap(f"我加的「{label}」这一步，您刚才的话里我没对上原话，是这个意思吗？", [nid]))

    if new_graph is graph:
        state["snapshots"].pop()  # nothing to undo this turn

    resolved = [g for g in out.get("resolved_gap_ids") or [] if isinstance(g, str)]
    if intent == "answer" and state.get("pending_gap_id"):
        resolved.append(state["pending_gap_id"])
    new_gaps = [review_gaps.model_gap(u["question"].strip()[:150], [i for i in (u.get("node_ids") or []) if isinstance(i, str)])
                for u in (out.get("new_uncertainties") or [])[:2]
                if isinstance(u, dict) and isinstance(u.get("question"), str) and u["question"].strip()
                and not any(j in u["question"] for j in _JARGON)]
    state["gaps"] = review_gaps.refresh(review_gaps.mark(state["gaps"], resolved, "resolved"), new_graph, mode=mode, new_model_gaps=new_gaps)
    result.graph = new_graph if new_graph is not graph else None

    if intent in ("satisfied", "reject"):
        return _final_confirm(state, new_graph, result, rejected=intent == "reject", model_tags=model_tags)
    if intent == "adopt":
        return _final_confirm(state, new_graph, result, model_tags=model_tags)
    if state["phase"] == "final_confirm" and state["mode"] in ("annotate", "arbitrate") and result.graph is None:
        # Still confirming; the person asked something that didn't change the graph.
        return _final_confirm(state, new_graph, result, model_tags=model_tags)
    preferred = _valid_question(out.get("question"), {g["id"] for g in offered})
    return _next_question(state, new_graph, result, preferred)


def progress(state: dict) -> float:
    """Explainable completion estimate for the workflow list: nothing before the first draft,
    then the share of clarification items settled, 100 once confirmed."""
    phase = state.get("phase")
    if phase == "narrative":
        return 0.0
    if phase == "done":
        return 100.0
    if phase == "final_confirm":
        return 95.0
    gaps = state.get("gaps") or []
    settled = sum(1 for g in gaps if g["status"] != "open")
    return round(40 + 50 * (settled / len(gaps) if gaps else 1), 1)


def after_regeneration(state: dict, graph: dict) -> TurnResult:
    """「刷新工作流图」in review mode: the graph was rebuilt from the whole transcript, so the
    clarification list is recomputed against it and the conversation continues from there."""
    state = copy.deepcopy(state)
    state["phase"] = "review"
    state["snapshots"] = []  # snapshots hold pre-refresh graphs; undo across a refresh would swap them back
    state["gaps"] = review_gaps.refresh(state.get("gaps") or [], graph, mode=state["mode"])
    result = TurnResult(changes=["根据整段对话重新整理了流程图"], graph=graph, state=state)
    return _next_question(state, graph, result, None)
