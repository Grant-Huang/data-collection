"""Mock Guide Service -- stands in for the real 7B "L" model from PRD 15.0/17.2 until one is
wired up (see IMPLEMENTATION_PLAN.md assumption 3). Same call signature a real model-backed
implementation would have: (session_state, expert_text) -> (assistant_reply, graph_ops,
next_question, new_state).

Honesty about what this mock does and doesn't do, since it matters for how it's read:
- Structural decisions (branch / parallel / merge / approval / retry) are read off the small
  fixed set of quick-reply chips from PRD section 18 -- pattern-matching the handful of chip
  strings is completely fine because the answer space really is that closed set.
- Content (node labels, roles) is taken verbatim from whatever the expert typed, with no NLU
  at all. It does not summarize, infer, or fill in anything the expert didn't say -- which
  happens to be the same "don't silently fabricate" rule the real model is required to follow
  (PRD 3.2), just satisfied here by construction rather than by a trained model actually
  understanding the text.
- It cannot handle expert input arriving out of the expected order (PRD 3.2's "if the expert
  volunteers later information early, extract it immediately" is a real-LLM capability this
  mock does not attempt). It always advances one fixed stage at a time.

Follow-up priorities referenced below (P0-P7) are PRD section 9.

Scenario / Case Context (IMPLEMENTATION_PLAN.md section 9.1, design/case_context_and_prior_
annotation_draft.md): before the original opening->trigger_detail flow, this module now asks
three "Scenario" questions (A-group: trigger/goal/success) and four "Case Context" questions
(B-group: known/unknown/constraints/resources). Per that draft's decision 1, the A-group's
"simple/detailed" mode chips are literally answer templates ("简单说："/"详细说：...——") the
expert types after -- no new frontend round trip needed, detail_level is read off which
prefix the submitted text starts with. Per decision 2, the B-group is multi-select chips
followed by one merged follow-up question when anything other than "无" is picked; "无" skips
straight to the next question. Node-level "why did you do that" rationale (the original
draft's C-group) is NOT implemented this round -- see IMPLEMENTATION_PLAN.md section 9.3.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

NODE_TYPE_LABELS = {
    "decision": "判断",
    "parallel_split": "并行拆分",
    "parallel_join": "并行汇合",
    "merge": "汇合",
    "approval": "审批",
}

# --- Scenario (A-group) -----------------------------------------------------------------

SCENARIO_CHIPS = {
    "scenario_trigger": ["简单说：", "详细说：时间、影响范围、怎么发现的——"],
    "scenario_goal": ["简单说：", "详细说：想达成什么、有什么顾虑——"],
    "scenario_success": ["简单说：", "详细说：设备/订单/人员分别是什么状态——"],
}

# stage -> (question that leads into it, chips to show)
SCENARIO_TRANSITIONS = {
    "scenario_trigger": ("当时最主要的目标是什么？", "scenario_goal"),
    "scenario_goal": ("如果这件事处理成功，应该是什么状态？", "scenario_success"),
}


def _detail_level(text: str) -> str:
    return "detailed" if text.strip().startswith("详细说") else "brief"


def _case_context_set(pending: dict, field: str, value: str) -> dict:
    cc = dict(pending.get("case_context", {}))
    cc[field] = value
    return {**pending, "case_context": cc}


def _case_context_set_detail(pending: dict, field: str, level: str) -> dict:
    cc = dict(pending.get("case_context", {}))
    levels = dict(cc.get("detail_level", {}))
    levels[field] = level
    cc["detail_level"] = levels
    return {**pending, "case_context": cc}


def _case_context_mark_skipped(pending: dict, field: str) -> dict:
    cc = dict(pending.get("case_context", {}))
    skipped = list(cc.get("skipped_fields", []))
    if field not in skipped:
        skipped.append(field)
    cc["skipped_fields"] = skipped
    cc.setdefault(field, "")
    return {**pending, "case_context": cc}


# --- Case Context (B-group) -------------------------------------------------------------

B_GROUP_CONFIG: dict[str, dict] = {
    "context_known": {
        "field": "known_info",
        "chips": ["设备/系统状态", "订单/生产计划信息", "过往类似案例", "他人反馈/汇报", "无"],
        "followups": {},
        "default_followup": "具体是什么信息？大概是什么时候、通过什么方式知道的？",
        "next_question": "哪些信息是不知道的？",
        "next_stage": "context_unknown",
    },
    "context_unknown": {
        "field": "unknown_info",
        "chips": ["故障/问题的根本原因", "影响范围有多大", "预计恢复/解决时间", "其他人的处理进展", "无"],
        "followups": {},
        "default_followup": "这些不确定，当时对你的判断或决策有什么影响？",
        "next_question": "当时有哪些限制？（时间、安全、物料、跨部门协调等方面）",
        "next_stage": "context_constraints",
    },
    "context_constraints": {
        "field": "constraints",
        "chips": ["时间紧", "安全风险", "缺备件/物料", "需要跨部门协调", "无"],
        "followups": {
            "时间紧": "当时给的时间窗口大概多久？",
            "安全风险": "具体是什么风险？",
            "缺备件/物料": "具体缺什么，大概什么时候能到？",
            "需要跨部门协调": "需要协调哪些部门？",
        },
        "default_followup": "具体是什么限制？",
        "next_question": "有哪些人或设备/资源可以帮忙、可用或不可用？",
        "next_stage": "context_resources",
    },
    "context_resources": {
        "field": "available_resources",
        "chips": ["同班组同事", "设备/工艺工程师", "其他产线产能", "上级授权", "无"],
        "followups": {},
        "default_followup": "具体是谁/是什么？当时状态如何（在场、可调用，还是暂时不可用）？",
        "next_question": None,
        "next_stage": "trigger_detail",  # last B-group question feeds into the original flow
    },
}


def _multiselect(text: str) -> list[str]:
    # Split only on the separators the frontend joins selections with ("、") plus the
    # obvious ASCII/full-width comma fallbacks for when the expert hand-edits the draft --
    # NOT on "/" or whitespace, since several chip labels contain "/" themselves
    # (e.g. "设备/系统状态", "缺备件/物料") and splitting on it breaks those apart.
    parts = re.split(r"[、,，]+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _b_group_advance(cfg: dict, pending: dict, ops: list[dict]) -> tuple[str, list[dict], dict, dict]:
    if cfg["next_stage"] == "trigger_detail":
        reply = "背景了解得差不多了，我们开始梳理你当时具体是怎么做的。当时是谁最先发现的？发现后第一件事做什么？"
        nq = {"target": "trigger_discovery", "priority": "P0", "question": reply, "chips": None}
        new_state = {"stage": "trigger_detail", "cursor": None, "pending": pending}
        return reply, ops, nq, new_state
    next_cfg = B_GROUP_CONFIG[cfg["next_stage"]]
    reply = cfg["next_question"]
    nq = {"target": "case_context_discovery", "priority": "P1", "question": reply,
          "chips": next_cfg["chips"], "chip_mode": "multi_select"}
    new_state = {"stage": cfg["next_stage"], "cursor": None, "pending": pending}
    return reply, ops, nq, new_state


def _handle_b_group_select(stage: str, text: str, pending: dict, ops: list[dict]) -> tuple[str, list[dict], dict, dict]:
    cfg = B_GROUP_CONFIG[stage]
    selected = _multiselect(text)
    if not selected or selected == ["无"]:
        pending = _case_context_mark_skipped(pending, cfg["field"])
        return _b_group_advance(cfg, pending, ops)
    pending = {**pending, "_b_selected": selected}
    followups = [cfg["followups"][s] for s in selected if s in cfg["followups"]]
    question = "；".join(followups) if followups else cfg["default_followup"]
    nq = {"target": "case_context_discovery", "priority": "P1", "question": question, "chips": None}
    new_state = {"stage": f"{stage}_clarify", "cursor": None, "pending": pending}
    return question, ops, nq, new_state


def _handle_b_group_clarify(stage: str, text: str, pending: dict, ops: list[dict]) -> tuple[str, list[dict], dict, dict]:
    base_stage = stage[: -len("_clarify")]
    cfg = B_GROUP_CONFIG[base_stage]
    selected = pending.get("_b_selected", [])
    combined = f"{'、'.join(selected)}：{text}" if selected else text
    pending = _case_context_set(pending, cfg["field"], combined)
    pending = {k: v for k, v in pending.items() if k != "_b_selected"}
    return _b_group_advance(cfg, pending, ops)


def initial_state() -> dict[str, Any]:
    return {"stage": "opening", "cursor": None, "pending": {}}


def initial_turn() -> tuple[str, dict[str, Any]]:
    reply = (
        "你好，我会把你讲的真实工作整理成一张流程图，不用你自己画图。"
        "请先回忆一件你亲自参与、比较熟悉的制造工作。"
    )
    next_question = {
        "target": "trigger_discovery",
        "priority": "P0",
        "question": reply,
        "chips": ["设备/质量异常", "标准生产工作", "持续改善", "工程/工艺变更"],
    }
    return reply, next_question


def _nid() -> str:
    return uuid.uuid4().hex[:8]


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(k in text for k in keywords)


def handle_turn(state: dict[str, Any], text: str) -> tuple[str, list[dict], dict | None, dict[str, Any]]:
    """Returns (assistant_reply, graph_ops, next_question_or_None, new_state).

    next_question is None only on the final ("review") turn -- the caller treats that as
    "nothing left to ask right now", matching PRD 3.5's move from "keep asking" to "final
    confirmation" once completion is high enough.
    """
    stage = state["stage"]
    cursor = state["cursor"]
    pending = state.get("pending", {})
    ops: list[dict] = []
    text = text.strip()

    if stage == "opening":
        reply = f"好，我先把它理解成一段「{text[:24]}」相关的经历。当时具体发生了什么？为什么需要处理这件事？"
        nq = {"target": "scenario_discovery", "priority": "P0", "question": reply,
              "chips": SCENARIO_CHIPS["scenario_trigger"]}
        new_state = {"stage": "scenario_trigger", "cursor": None, "pending": {"category": text}}
        return reply, ops, nq, new_state

    if stage in SCENARIO_TRANSITIONS:
        level = _detail_level(text)
        pending = _case_context_set(pending, stage, text)
        pending = _case_context_set_detail(pending, stage, level)
        question, next_stage = SCENARIO_TRANSITIONS[stage]
        nq = {"target": "scenario_discovery", "priority": "P0", "question": question,
              "chips": SCENARIO_CHIPS[next_stage]}
        new_state = {"stage": next_stage, "cursor": None, "pending": pending}
        return question, ops, nq, new_state

    if stage == "scenario_success":
        level = _detail_level(text)
        pending = _case_context_set(pending, "scenario_success", text)
        pending = _case_context_set_detail(pending, "scenario_success", level)
        first_cfg = B_GROUP_CONFIG["context_known"]
        reply = "了解背景之后，再确认几个细节。当时你知道哪些信息？"
        nq = {"target": "case_context_discovery", "priority": "P1", "question": reply,
              "chips": first_cfg["chips"], "chip_mode": "multi_select"}
        new_state = {"stage": "context_known", "cursor": None, "pending": pending}
        return reply, ops, nq, new_state

    if stage in B_GROUP_CONFIG:
        return _handle_b_group_select(stage, text, pending, ops)

    if stage.endswith("_clarify") and stage[: -len("_clarify")] in B_GROUP_CONFIG:
        return _handle_b_group_clarify(stage, text, pending, ops)

    if stage == "trigger_detail":
        start_id, first_id = _nid(), _nid()
        ops += [
            {"op": "add_node", "node": {"node_id": start_id, "node_type": "start", "label": "开始",
                                         "source_turn_ids": [], "confidence": 0.9, "expert_confirmed": False}},
            {"op": "set_start", "node_id": start_id},
            {"op": "add_node", "node": {"node_id": first_id, "node_type": "activity", "label": text[:40],
                                         "source_turn_ids": [], "confidence": 0.9, "expert_confirmed": False}},
            {"op": "add_edge", "edge": {"edge_id": _nid(), "from": start_id, "to": first_id,
                                         "edge_type": "normal", "confidence": 0.9, "expert_confirmed": False}},
        ]
        reply = "明白，我先记下这一步。然后呢？下一步是谁做什么？"
        nq = {"target": "main_path_discovery", "priority": "P0", "question": reply, "chips": None}
        new_state = {"stage": "main_path", "cursor": first_id, "pending": pending}
        return reply, ops, nq, new_state

    if stage == "main_path":
        step_id = _nid()
        ops += [
            {"op": "add_node", "node": {"node_id": step_id, "node_type": "activity", "label": text[:40],
                                         "source_turn_ids": [], "confidence": 0.85, "expert_confirmed": False}},
            {"op": "add_edge", "edge": {"edge_id": _nid(), "from": cursor, "to": step_id,
                                         "edge_type": "normal", "confidence": 0.85, "expert_confirmed": False}},
        ]
        reply = "这里是不是只有一种处理方式，还是不同情况下会走不同方向？"
        nq = {"target": "branch_discovery", "priority": "P1", "question": reply,
              "chips": ["只有一种处理方式", "会走不同方向", "不确定，再想想"]}
        new_state = {"stage": "branch_check", "cursor": step_id, "pending": pending}
        return reply, ops, nq, new_state

    if stage == "branch_check":
        if _contains_any(text, ["不同方向", "分支", "看情况"]):
            decision_id = _nid()
            ops += [
                {"op": "add_node", "node": {"node_id": decision_id, "node_type": "decision",
                                             "label": "判断", "decision_question": "走哪个方向？",
                                             "source_turn_ids": [], "confidence": 0.8, "expert_confirmed": False}},
                {"op": "add_edge", "edge": {"edge_id": _nid(), "from": cursor, "to": decision_id,
                                             "edge_type": "normal", "confidence": 0.8, "expert_confirmed": False}},
            ]
            reply = "第一种情况，条件是什么？接下来做什么？"
            nq = {"target": "branch_condition_a", "priority": "P1", "question": reply, "chips": None}
            new_state = {"stage": "branch_condition_a", "cursor": decision_id, "pending": pending}
            return reply, ops, nq, new_state
        # single path: skip decision node, go straight to the parallel-check question
        reply = "好，这里没有分支。接下来这一步，是不是有两件事可以同时做，还是先后做？"
        nq = {"target": "parallel_merge_discovery", "priority": "P2", "question": reply,
              "chips": ["先后做", "同时做", "这里没有并行的事"]}
        new_state = {"stage": "parallel_check", "cursor": cursor, "pending": pending}
        return reply, ops, nq, new_state

    if stage == "branch_condition_a":
        condition, rest = _split_condition(text)
        tail_id = _nid()
        ops += [
            {"op": "add_node", "node": {"node_id": tail_id, "node_type": "activity", "label": rest or text[:40],
                                         "source_turn_ids": [], "confidence": 0.8, "expert_confirmed": False}},
            {"op": "add_edge", "edge": {"edge_id": _nid(), "from": cursor, "to": tail_id,
                                         "edge_type": "conditional", "condition": condition,
                                         "confidence": 0.8, "expert_confirmed": False}},
        ]
        reply = "另一种情况呢？条件是什么，接下来做什么？"
        nq = {"target": "branch_condition_b", "priority": "P1", "question": reply, "chips": None}
        new_state = {"stage": "branch_condition_b", "cursor": cursor,
                      "pending": {**pending, "branch_a_tail": tail_id}}
        return reply, ops, nq, new_state

    if stage == "branch_condition_b":
        condition, rest = _split_condition(text)
        tail_id = _nid()
        ops += [
            {"op": "add_node", "node": {"node_id": tail_id, "node_type": "activity", "label": rest or text[:40],
                                         "source_turn_ids": [], "confidence": 0.8, "expert_confirmed": False}},
            {"op": "add_edge", "edge": {"edge_id": _nid(), "from": cursor, "to": tail_id,
                                         "edge_type": "conditional", "condition": condition,
                                         "confidence": 0.8, "expert_confirmed": False}},
        ]
        reply = "这两条路径处理完之后，是各自继续，还是要汇总后再进入同一步？"
        nq = {"target": "parallel_merge_discovery", "priority": "P3", "question": reply,
              "chips": ["各自继续", "汇总后再决定", "不确定，再想想"]}
        new_state = {"stage": "merge_check", "cursor": None,
                      "pending": {**pending, "branch_a_tail": pending.get("branch_a_tail"), "branch_b_tail": tail_id}}
        return reply, ops, nq, new_state

    if stage == "merge_check":
        a_tail, b_tail = pending.get("branch_a_tail"), pending.get("branch_b_tail")
        if _contains_any(text, ["汇总", "同一步", "一起"]):
            merge_id = _nid()
            ops += [
                {"op": "add_node", "node": {"node_id": merge_id, "node_type": "merge", "label": "汇合",
                                             "source_turn_ids": [], "confidence": 0.8, "expert_confirmed": False}},
                {"op": "add_edge", "edge": {"edge_id": _nid(), "from": a_tail, "to": merge_id,
                                             "edge_type": "merge", "confidence": 0.8, "expert_confirmed": False}},
                {"op": "add_edge", "edge": {"edge_id": _nid(), "from": b_tail, "to": merge_id,
                                             "edge_type": "merge", "confidence": 0.8, "expert_confirmed": False}},
            ]
            cursor_after = merge_id
        else:
            cursor_after = a_tail  # "各自继续": keep going from the first branch, second tail gets its own end later
        reply = "这两件事（比如设备检查和工艺检查这类）是先后做，还是可以同时进行？"
        nq = {"target": "parallel_merge_discovery", "priority": "P2", "question": reply,
              "chips": ["先后做", "同时做", "这里没有并行的事"]}
        new_state = {"stage": "parallel_check", "cursor": cursor_after,
                      "pending": {**pending, "loose_end": b_tail if cursor_after != b_tail and not _contains_any(text, ["汇总", "同一步", "一起"]) else None}}
        return reply, ops, nq, new_state

    if stage == "parallel_check":
        if _contains_any(text, ["同时"]):
            split_id = _nid()
            ops += [
                {"op": "add_node", "node": {"node_id": split_id, "node_type": "parallel_split", "label": "并行拆分",
                                             "source_turn_ids": [], "confidence": 0.8, "expert_confirmed": False}},
                {"op": "add_edge", "edge": {"edge_id": _nid(), "from": cursor, "to": split_id,
                                             "edge_type": "normal", "confidence": 0.8, "expert_confirmed": False}},
            ]
            reply = "第一项并行的工作具体是什么？谁做？"
            nq = {"target": "parallel_merge_discovery", "priority": "P2", "question": reply, "chips": None}
            new_state = {"stage": "parallel_branch_a", "cursor": split_id, "pending": pending}
            return reply, ops, nq, new_state
        # single path or "先后做": treat as a normal step and move on to approval question
        reply = "这一步做完，是直接继续，还是需要谁确认一下才能往下走？"
        nq = {"target": "actor_system_discovery", "priority": "P4", "question": reply,
              "chips": ["直接继续", "需要确认", "不确定，再想想"]}
        new_state = {"stage": "approval_check", "cursor": cursor, "pending": pending}
        return reply, ops, nq, new_state

    if stage == "parallel_branch_a":
        tail_id = _nid()
        ops += [
            {"op": "add_node", "node": {"node_id": tail_id, "node_type": "activity", "label": text[:40],
                                         "source_turn_ids": [], "confidence": 0.8, "expert_confirmed": False}},
            {"op": "add_edge", "edge": {"edge_id": _nid(), "from": cursor, "to": tail_id,
                                         "edge_type": "parallel", "confidence": 0.8, "expert_confirmed": False}},
        ]
        reply = "第二项并行的工作呢？"
        nq = {"target": "parallel_merge_discovery", "priority": "P2", "question": reply, "chips": None}
        new_state = {"stage": "parallel_branch_b", "cursor": cursor,
                      "pending": {**pending, "par_a_tail": tail_id}}
        return reply, ops, nq, new_state

    if stage == "parallel_branch_b":
        tail_id = _nid()
        join_id = _nid()
        a_tail = pending.get("par_a_tail")
        ops += [
            {"op": "add_node", "node": {"node_id": tail_id, "node_type": "activity", "label": text[:40],
                                         "source_turn_ids": [], "confidence": 0.8, "expert_confirmed": False}},
            {"op": "add_edge", "edge": {"edge_id": _nid(), "from": cursor, "to": tail_id,
                                         "edge_type": "parallel", "confidence": 0.8, "expert_confirmed": False}},
            {"op": "add_node", "node": {"node_id": join_id, "node_type": "parallel_join", "label": "并行汇合",
                                         "source_turn_ids": [], "confidence": 0.8, "expert_confirmed": False}},
            {"op": "add_edge", "edge": {"edge_id": _nid(), "from": a_tail, "to": join_id,
                                         "edge_type": "parallel", "confidence": 0.8, "expert_confirmed": False}},
            {"op": "add_edge", "edge": {"edge_id": _nid(), "from": tail_id, "to": join_id,
                                         "edge_type": "parallel", "confidence": 0.8, "expert_confirmed": False}},
        ]
        reply = "两边完成之后，是直接继续，还是需要谁确认一下才能往下走？"
        nq = {"target": "actor_system_discovery", "priority": "P4", "question": reply,
              "chips": ["直接继续", "需要确认", "不确定，再想想"]}
        new_state = {"stage": "approval_check", "cursor": join_id, "pending": pending}
        return reply, ops, nq, new_state

    if stage == "approval_check":
        if _contains_any(text, ["需要确认", "需要"]):
            approval_id = _nid()
            ops += [
                {"op": "add_node", "node": {"node_id": approval_id, "node_type": "approval", "label": "审批",
                                             "source_turn_ids": [], "confidence": 0.8, "expert_confirmed": False}},
                {"op": "add_edge", "edge": {"edge_id": _nid(), "from": cursor, "to": approval_id,
                                             "edge_type": "approval", "confidence": 0.8, "expert_confirmed": False}},
            ]
            reply = "具体是谁有权确认/批准？"
            nq = {"target": "actor_system_discovery", "priority": "P4", "question": reply, "chips": None}
            new_state = {"stage": "approval_who", "cursor": approval_id, "pending": pending}
            return reply, ops, nq, new_state
        reply = "如果结果不合格，会不会重新回去做前面某一段？"
        nq = {"target": "rule_judgement_discovery", "priority": "P5", "question": reply,
              "chips": ["会返工", "不会，流程到这里结束", "不确定，再想想"]}
        new_state = {"stage": "retry_check", "cursor": cursor, "pending": pending}
        return reply, ops, nq, new_state

    if stage == "approval_who":
        ops.append({"op": "update_node", "node_id": cursor,
                    "patch": {"actor_roles": [text[:20]], "label": f"审批（{text[:20]}）"}})
        reply = "如果结果不合格，会不会重新回去做前面某一段？"
        nq = {"target": "rule_judgement_discovery", "priority": "P5", "question": reply,
              "chips": ["会返工", "不会，流程到这里结束", "不确定，再想想"]}
        new_state = {"stage": "retry_check", "cursor": cursor, "pending": pending}
        return reply, ops, nq, new_state

    if stage == "retry_check":
        # "会" alone used to be in this keyword list, which wrongly matched the negative
        # chip "不会，流程到这里结束" (substring containment: "不会" contains "会"). Match
        # only on the actual positive-answer text.
        if _contains_any(text, ["会返工"]) or (text.startswith("会") and not text.startswith("不会")):
            reply = "具体是回到前面哪一步重新做？"
            nq = {"target": "rule_judgement_discovery", "priority": "P5", "question": reply, "chips": None}
            new_state = {"stage": "retry_target", "cursor": cursor, "pending": pending}
            return reply, ops, nq, new_state
        reply = "整个流程正常结束的标志是什么？"
        nq = {"target": "end_condition_discovery", "priority": "P0", "question": reply, "chips": None}
        new_state = {"stage": "end_condition", "cursor": cursor, "pending": pending}
        return reply, ops, nq, new_state

    if stage == "retry_target":
        # Best-effort: point the retry back at the earliest main-path node we created, since
        # this mock has no real coreference resolution to match the expert's free-text
        # description of "which step" against node labels (PRD 3.2 forbids guessing, so when
        # we can't confidently resolve it we say so honestly rather than picking one).
        ops.append({
            "op": "set_retry_semantics",
            "node_id": cursor,
            "retry_semantics": {"enabled": True, "rework_reference_node_id": None,
                                 "condition": "结果不合格", "description": text[:60]},
        })
        reply = "好，已经记下返工的说明（暂未自动定位到具体节点，提交前可以在图上手动指认）。整个流程正常结束的标志是什么？"
        nq = {"target": "end_condition_discovery", "priority": "P0", "question": reply, "chips": None}
        new_state = {"stage": "end_condition", "cursor": cursor, "pending": pending}
        return reply, ops, nq, new_state

    if stage == "end_condition":
        end_id = _nid()
        ops += [
            {"op": "add_node", "node": {"node_id": end_id, "node_type": "end", "label": text[:40],
                                         "source_turn_ids": [], "confidence": 0.9, "expert_confirmed": False}},
            {"op": "add_edge", "edge": {"edge_id": _nid(), "from": cursor, "to": end_id,
                                         "edge_type": "normal", "confidence": 0.9, "expert_confirmed": False}},
            {"op": "set_end", "node_id": end_id},
        ]
        loose_end = pending.get("loose_end")
        if loose_end:
            ops += [
                {"op": "add_edge", "edge": {"edge_id": _nid(), "from": loose_end, "to": end_id,
                                             "edge_type": "normal", "confidence": 0.7, "expert_confirmed": False}},
            ]
        reply = "整理得差不多了。我已经把这张流程图画出来了，麻烦你在右边看一下有没有地方不对。"
        # Reset pending to drop stage-scratch state (branch tails etc.) but keep case_context --
        # it was collected before any of that scratch state existed and has nothing to do with it.
        new_state = {"stage": "review", "cursor": None, "pending": {"case_context": pending.get("case_context", {})}}
        return reply, ops, None, new_state

    # stage == "review" or unknown: nothing more to structurally extract
    reply = "已经在最终确认阶段了——有需要修改的地方，直接说，我来改图；没问题的话可以点「确认并提交」。"
    return reply, ops, None, state


def _split_condition(text: str) -> tuple[str, str]:
    """Best-effort split of "<condition>，<what happens>" into (condition, rest). If there's
    no clear separator, the whole thing is treated as the condition and rest is left for the
    caller to fall back to the raw text -- again: no guessing, just an honest "couldn't split
    this" fallback.
    """
    for sep in ("，", ",", "：", ":"):
        if sep in text:
            head, _, tail = text.partition(sep)
            return head.strip(), tail.strip()
    return text.strip(), ""
