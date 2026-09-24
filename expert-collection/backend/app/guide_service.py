"""Mock Guide Service -- stands in for the real 7B "L" model from PRD 15.0/17.2 until one is
wired up (see IMPLEMENTATION_PLAN.md assumption 3). Same call signature a real model-backed
implementation would have: (session_state, expert_text) -> (assistant_reply, graph_ops,
next_question, new_state).

Honesty about what this mock does and doesn't do, since it matters for how it's read:
- Structural decisions (branch / parallel / merge / approval / retry) are read off the small
  fixed set of quick-reply chips from PRD section 18 -- pattern-matching the handful of chip
  strings is completely fine because the answer space really is that closed set.
- Content (node labels, roles) is built only from words the expert actually typed, with no
  NLU, summarization or paraphrase. It does not infer or fill in anything the expert didn't
  say -- which happens to be the same "don't silently fabricate" rule the real model is
  required to follow (PRD 3.2), just satisfied here by construction rather than by a trained
  model actually understanding the text. Within that constraint, one piece of free text can
  still describe more than one step ("先记录系统，然后通知班组长") or mix in scene-setting
  that isn't a step at all ("是质检员发现的，..."). `_extract_step_clauses` below draws the
  line at a fixed, closed set of coordinating connectors and a fixed "who discovered this"
  prefix pattern -- the same kind of pattern-matching-over-a-closed-set already used for chip
  parsing, not general sentence understanding -- so each resulting node label is the clause
  about that one action, not the whole compound sentence and not a fabricated summary of it.
- It cannot handle expert input arriving out of the expected order (PRD 3.2's "if the expert
  volunteers later information early, extract it immediately" is a real-LLM capability this
  mock does not attempt). It always advances one fixed stage at a time -- including when the
  expert is actually correcting something they just said ("哦，我说错了，..."): this mock has
  no way to tell "that's a retraction of the last node(s)" from "that's the next step", so a
  correction still gets recorded forward as a new step, with whatever preamble the expert used
  to flag it as a correction left in. Genuinely detecting and undoing a correction needs real
  language understanding (KNOWN GAP -- see IMPLEMENTATION_PLAN.md section 13 -- deliberately
  left for the real L model rather than approximated with keyword matching here, since
  "was this a correction" is exactly the kind of judgment call a closed keyword list gets
  wrong often enough to do more harm than the bug it's meant to fix).
- One thing this mock *does* ask about rather than silently guess: when a compound sentence
  splits on "并"/"并且"/"同时" specifically (as opposed to "然后"/"、", which read
  unambiguously as sequential), whether the two actions were done one after another or at the
  same time is genuinely ambiguous from the words alone -- so `_needs_parallel_clarify` routes
  through a "先后做/同时做" clarifying question (reusing the same chips PRD 18 already defines
  for this fork elsewhere) instead of defaulting to either shape.

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

Real LLM integration (IMPLEMENTATION_PLAN.md section 14, §15.1-①(b)): `_understand_step`
is the one place all six step-creating stages go through to turn expert free text into
(clauses, relationship). When the `guide_service` slot is enabled and configured with a
reachable endpoint, it calls the real model through `llm_client.py` with a prompt that
constrains it to the exact same contract the rule-based path already promises (clauses come
from the expert's own words, no fabrication; ambiguous 并/同时 splits still get asked about,
never silently guessed -- that was a product decision, not just a Mock limitation, so it
holds for the real model too). Any failure at all -- not configured, disabled, network/
timeout, malformed JSON, wrong shape -- falls back to the original regex-based
`_extract_step_clauses`/`_needs_parallel_clarify` pair rather than surfacing an error to the
expert or crashing the turn; the two paths are called through the same `_understand_step`
so callers never need to know which one actually ran.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from . import llm_client
from . import settings as app_settings

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


def handle_turn(state: dict[str, Any], text: str, turn_id: str | None = None,
                 skip_correction_check: bool = False
                 ) -> tuple[str, list[dict], dict | None, dict[str, Any]]:
    """Returns (assistant_reply, graph_ops, next_question_or_None, new_state).

    next_question is None only on the final ("review") turn -- the caller treats that as
    "nothing left to ask right now", matching PRD 3.5's move from "keep asking" to "final
    confirmation" once completion is high enough.

    `turn_id` (IMPLEMENTATION_PLAN.md section 14, §15.1-①(c)) is stamped onto every
    `add_node`/`add_edge` op's `source_turn_ids` this call produces, so a later turn can be
    traced back to and undone -- see the "correction/rollback" stages below. Callers that
    don't pass one (or don't need undo) get the previous behavior (`source_turn_ids: []`).

    `skip_correction_check` is for routers/expert_workflows.py to set when it's re-processing
    an expert's original text after they picked "不是，这是新的一步" from the turn picker (see
    "awaiting_turn_selection" there) -- without it, re-running the exact same text through the
    exact same stage could flag it as a correction again and loop.
    """
    reply, ops, nq, new_state = _dispatch_turn(state, text, skip_correction_check=skip_correction_check)
    if turn_id:
        for op in ops:
            if op.get("op") == "add_node":
                op["node"]["source_turn_ids"] = [turn_id]
            elif op.get("op") == "add_edge":
                op["edge"]["source_turn_ids"] = [turn_id]
    return reply, ops, nq, new_state


def _dispatch_turn(state: dict[str, Any], text: str, skip_correction_check: bool = False
                    ) -> tuple[str, list[dict], dict | None, dict[str, Any]]:
    """The actual FSM dispatch, previously named `handle_turn`. `skip_correction_check` is
    used only when re-processing an expert's original text after the expert picked "不是，
    这是新的一步" from the correction turn picker (see routers/expert_workflows.py's handling
    of the "awaiting_turn_selection" stage) -- without it, re-running the exact same text
    through the exact same stage could flag it as a correction again and loop.
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

    if stage == "compound_parallel_clarify":
        return _resolve_parallel_clarify(text, pending, ops)

    if stage == "trigger_detail":
        understanding = (_understand_step(text) if skip_correction_check
                          else _understand_step_and_check_correction(text))
        if not skip_correction_check and understanding.get("is_correction"):
            return _start_correction_pick(stage, cursor, pending, text)
        start_id = _nid()
        ops += [
            {"op": "add_node", "node": {"node_id": start_id, "node_type": "start", "label": "开始",
                                         "source_turn_ids": [], "confidence": 0.9, "expert_confirmed": False}},
            {"op": "set_start", "node_id": start_id},
        ]
        return _apply_understanding("trigger_detail", start_id, understanding, pending, ops, confidence=0.9)

    if stage == "main_path":
        understanding = (_understand_step(text) if skip_correction_check
                          else _understand_step_and_check_correction(text))
        if not skip_correction_check and understanding.get("is_correction"):
            return _start_correction_pick(stage, cursor, pending, text)
        return _apply_understanding("main_path", cursor, understanding, pending, ops)

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
        step_text = rest or text
        understanding = (_understand_step(step_text) if skip_correction_check
                          else _understand_step_and_check_correction(step_text))
        if not skip_correction_check and understanding.get("is_correction"):
            return _start_correction_pick(stage, cursor, pending, text)
        return _apply_understanding("branch_condition_a", cursor, understanding, pending, ops,
                                     edge_type="conditional", condition=condition, confidence=0.8)

    if stage == "branch_condition_b":
        condition, rest = _split_condition(text)
        step_text = rest or text
        understanding = (_understand_step(step_text) if skip_correction_check
                          else _understand_step_and_check_correction(step_text))
        if not skip_correction_check and understanding.get("is_correction"):
            return _start_correction_pick(stage, cursor, pending, text)
        return _apply_understanding("branch_condition_b", cursor, understanding, pending, ops,
                                     edge_type="conditional", condition=condition, confidence=0.8)

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
        # No illustrative example here on purpose: this reply text is stored verbatim in the
        # turn transcript, and an example like "比如设备检查和工艺检查" sitting right next to
        # a real question reads, on a later pass over the transcript (rendering, export, or a
        # real LLM re-deriving structure from conversation history), exactly like something
        # the expert actually said -- there is nothing that marks it as "just an example" once
        # it is plain text in the log. Keep this question generic so there is no fabricated
        # content anywhere in the transcript for anything downstream to mistake for real input.
        reply = "这两件事是先后做，还是可以同时进行？"
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
        understanding = (_understand_step(text) if skip_correction_check
                          else _understand_step_and_check_correction(text))
        if not skip_correction_check and understanding.get("is_correction"):
            return _start_correction_pick(stage, cursor, pending, text)
        return _apply_understanding("parallel_branch_a", cursor, understanding, pending, ops,
                                     edge_type="parallel", confidence=0.8)

    if stage == "parallel_branch_b":
        understanding = (_understand_step(text) if skip_correction_check
                          else _understand_step_and_check_correction(text))
        if not skip_correction_check and understanding.get("is_correction"):
            return _start_correction_pick(stage, cursor, pending, text)
        return _apply_understanding("parallel_branch_b", cursor, understanding, pending, ops,
                                     edge_type="parallel", confidence=0.8)

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


_DISCOVERY_PREFIX_RE = re.compile(
    r"^(是)?[^，,。]{0,20}(发现的|发现|反馈的|反馈|报告的|报告|上报的|上报)[，,、]\s*"
)

_STEP_FILLER_PREFIX_RE = re.compile(
    r"^(第一时间就|第一时间|立即就|立即|马上就|马上|随即就|随即|随后就|随后|接着就|接着|然后就|然后|先|再)\s*"
)

# Fixed, closed set of coordinating connectors this mock treats as "these join two
# actions", same spirit as the fixed chip vocabulary used elsewhere (PRD section 18).
_STEP_SPLIT_RE = re.compile(r"[，,]?\s*(?:并且|并|同时|然后)\s*|、")


def _extract_step_clauses(text: str, max_steps: int = 2) -> list[str]:
    """Best-effort split of one piece of expert free text into 1-2 short step
    descriptions -- honestly within the Honest Mock limits described in the module
    docstring:
    - This is NOT summarization or paraphrase. Every word in the output still comes
      from the expert's own text. Two things are removed, both mechanically: (a) an
      optional leading "who discovered this / how it was noticed" clause, which
      belongs to scenario_trigger / case_context (already asked for separately) and
      is not itself a step; (b) leading timing filler words ("第一时间就", "随后",
      ...) trimmed off the front of each resulting clause so the label reads as an
      action ("记录系统") rather than a raw sentence fragment ("第一时间就记录系统").
    - The split point is a fixed small set of coordinating connectors ("并"/"同时"/
      "、"), not general clause parsing -- if the expert's phrasing doesn't use one
      of these, this function makes no attempt to guess a boundary and returns the
      text as a single clause, same as the old verbatim behaviour.
    - Capped at `max_steps` clauses: anything past the (max_steps-1)th connector is
      folded back into the last clause rather than silently dropped, since real
      free text can list three or more actions and this mock's node-per-message
      model needs a bound somewhere.
    """
    cleaned = _DISCOVERY_PREFIX_RE.sub("", text.strip())
    parts = [p.strip() for p in _STEP_SPLIT_RE.split(cleaned) if p and p.strip()]
    if not parts:
        parts = [cleaned]
    if len(parts) > max_steps:
        parts = parts[: max_steps - 1] + ["、".join(parts[max_steps - 1:])]
    result = []
    for p in parts:
        p = _STEP_FILLER_PREFIX_RE.sub("", p).strip("，, ").strip()
        if p:
            result.append(p[:40])
    return result or [text.strip()[:40]]


# Coordinating connectors genuinely ambiguous between "one after another" and "at the same
# time" -- unlike "然后" (clearly sequential) or "、" (a plain enumeration, treated as
# sequential same as before). Only a split on one of these gets an extra clarifying question
# (see _needs_parallel_clarify) instead of silently defaulting to sequential.
_AMBIGUOUS_CONNECTOR_RE = re.compile(r"并且|并|同时")


def _needs_parallel_clarify(text: str) -> bool:
    """True when `_extract_step_clauses` would split `text` into exactly two clauses AND
    the connector responsible for that split is one of the ambiguous ones above. "记录系统
    并通知班组长" could honestly mean either "do A then B" or "do A and B at the same time"
    -- this mock has no semantic understanding to tell which, so rather than silently
    guessing sequential (which is all it used to do), it asks the same 先后做/同时做
    question PRD 18 already uses elsewhere for exactly this fork.
    """
    if len(_extract_step_clauses(text)) != 2:
        return False
    cleaned = _DISCOVERY_PREFIX_RE.sub("", text.strip())
    m = _STEP_SPLIT_RE.search(cleaned)
    return bool(m and _AMBIGUOUS_CONNECTOR_RE.search(m.group(0)))


_STEP_UNDERSTANDING_SYSTEM_PROMPT = """你是一个制造业专家访谈助手的解析模块，只负责把专家刚才说的一句话解析成结构化 JSON，不做总结、改写，也不能编造专家没说过的内容——clauses 里的每个字都必须能在专家原话里找到依据。

只输出一个 JSON object，字段：
- "clauses"：字符串数组。每个元素是专家描述的一个具体动作步骤，用专家自己的措辞提炼（去掉"是谁发现的/怎么知道的"这类背景交代、去掉"第一时间就"这类时序填充词），不要整句话不加处理地原样放进去。如果整句话只描述一件事，返回只有一个元素的数组。
- "relationship"：当 clauses 长度 >= 2 时，说明这些步骤之间的关系："serial"（先后顺序做）、"parallel"（同时做）、"ambiguous"（原话没说清楚，需要跟专家确认，不要自己猜）。clauses 长度为 1 时固定填 "serial"。

只输出 JSON，不要有任何其他文字。"""


def _is_subsequence(needle: str, haystack: str) -> bool:
    it = iter(haystack)
    return all(ch in it for ch in needle)


def _clauses_are_grounded(clauses: list[str], text: str) -> bool:
    """The system prompt *tells* the model every clause must be traceable to the expert's own
    words, but a prompt instruction is not an enforcement mechanism -- a model can (and, on
    this exact question, has been observed to) answer with a plausible-sounding fabricated
    example instead of extracting from `text`. This is the same "the model's output must be
    checked, not trusted" rule `anonymize.py::_is_subsequence` and `explain.py::
    _no_fabricated_numbers` already apply to their own LLM calls -- this module was the one
    place that had the honesty claim in its prompt but no code-level check backing it up.
    Each clause must be a character subsequence of `text` (same characters, same order,
    filler/background words in between may be skipped -- exactly what "提炼" is supposed to
    do), not merely returned as similar-sounding invented content.
    """
    return all(_is_subsequence(c, text) for c in clauses)


def _llm_understand_step(text: str, slot_config: dict) -> dict | None:
    """Returns None on ANY failure (not configured, network/timeout, malformed output, wrong
    shape, or a clause that isn't actually grounded in `text`) so the caller falls back to the
    rule-based path -- never raises, per llm_client.py's "must not crash or hang the turn" rule.
    """
    try:
        parsed = llm_client.chat_completion_json(slot_config, [
            {"role": "system", "content": _STEP_UNDERSTANDING_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ])
    except llm_client.LLMError:
        return None

    clauses = parsed.get("clauses")
    if (not isinstance(clauses, list) or not clauses
            or not all(isinstance(c, str) and c.strip() for c in clauses)):
        return None
    clauses = [c.strip()[:60] for c in clauses]
    if not _clauses_are_grounded(clauses, text):
        return None

    relationship = parsed.get("relationship") if len(clauses) >= 2 else "serial"
    if relationship not in ("serial", "parallel", "ambiguous"):
        return None

    return {"clauses": clauses, "relationship": relationship}


def _understand_step(text: str) -> dict:
    """The one place all six step-creating stages go through to turn expert free text into
    {"clauses": [...], "relationship": "serial"|"parallel"|"ambiguous"}. Prefers a real LLM
    call (via the `guide_service` slot) when it's enabled and configured; falls back to the
    original regex-based `_extract_step_clauses`/`_needs_parallel_clarify` pair on any
    failure, so callers never need to know or care which path actually ran.
    """
    slot_config = app_settings.resolve_slot_for_call(app_settings.get_effective_settings(), "guide_service")
    if slot_config.get("enabled") and slot_config.get("endpoint") and slot_config.get("model_name"):
        result = _llm_understand_step(text, slot_config)
        if result is not None:
            return result
    clauses = _extract_step_clauses(text)
    relationship = "ambiguous" if _needs_parallel_clarify(text) else "serial"
    return {"clauses": clauses, "relationship": relationship}


_CORRECTION_SYSTEM_PROMPT = """你是一个制造业专家访谈助手的解析模块。除了把专家这句话解析成步骤描述之外，你还要判断一件事：专家这句话主要是在更正/撤回自己刚才说过的内容（比如"我说错了""不对，应该是""刚才说错了"这类），还是在正常回答当前问题、描述新的一步。

只输出一个 JSON object，字段：
- "is_correction"：boolean。true 表示这句话主要是在更正/撤回之前的内容。只有整体意思确实是在更正时才填 true——文字里出现"不对"这类词，但整体还是在正常描述业务事实（比如"这个判断标准不对称"），要填 false，不能只看字面关键词。
- "clauses"：字符串数组，规则跟 _understand_step 一样（提炼、去掉背景交代和时序填充词）。is_correction 为 true 时，这里放这句话里能看出来的、专家想要更正成的新描述，取不到就放一个整体概括。
- "relationship"："serial"/"parallel"/"ambiguous"，规则同上，clauses 长度 1 时固定 "serial"。

只输出 JSON，不要有任何其他文字。"""


def _llm_understand_step_and_correction(text: str, slot_config: dict) -> dict | None:
    try:
        parsed = llm_client.chat_completion_json(slot_config, [
            {"role": "system", "content": _CORRECTION_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ])
    except llm_client.LLMError:
        return None

    is_correction = parsed.get("is_correction")
    if not isinstance(is_correction, bool):
        return None

    clauses = parsed.get("clauses")
    if (not isinstance(clauses, list) or not clauses
            or not all(isinstance(c, str) and c.strip() for c in clauses)):
        return None
    clauses = [c.strip()[:60] for c in clauses]
    if not _clauses_are_grounded(clauses, text):
        return None

    relationship = parsed.get("relationship") if len(clauses) >= 2 else "serial"
    if relationship not in ("serial", "parallel", "ambiguous"):
        return None

    return {"clauses": clauses, "relationship": relationship, "is_correction": is_correction}


def _understand_step_and_check_correction(text: str) -> dict:
    """Same contract as `_understand_step`, plus an `is_correction` flag -- whether this turn
    reads like the expert retracting/correcting something they just said rather than
    describing the next step. Reliably telling those apart needs real semantic judgment a
    keyword list cannot do safely (IMPLEMENTATION_PLAN.md section 13's known-gap decision:
    a closed keyword list both false-positives on ordinary text and false-negatives on
    unlisted phrasings) -- so the rule-based fallback always reports `is_correction: False`,
    identical to this module's behavior before this capability existed. Only call this from
    the six step-creating stages when `skip_correction_check` is False; a caller re-processing
    text after the expert already declined the "was this a correction?" prompt should call
    `_understand_step` instead, to avoid asking the same question twice on the same text.
    """
    slot_config = app_settings.resolve_slot_for_call(app_settings.get_effective_settings(), "guide_service")
    if slot_config.get("enabled") and slot_config.get("endpoint") and slot_config.get("model_name"):
        result = _llm_understand_step_and_correction(text, slot_config)
        if result is not None:
            return result
    clauses = _extract_step_clauses(text)
    relationship = "ambiguous" if _needs_parallel_clarify(text) else "serial"
    return {"clauses": clauses, "relationship": relationship, "is_correction": False}


def _start_correction_pick(stage: str, cursor: str | None, pending: dict, text: str
                            ) -> tuple[str, list[dict], dict, dict]:
    """The model flagged this turn as a correction of something the expert already said.
    Rather than trust that judgment silently -- a false positive here would mean silently
    discarding graph content the expert didn't actually want removed -- ask first, the same
    "never auto-execute a destructive read of the expert's intent" rule this file already
    applies to chip answers.

    This asks in one step, not two: the confirm question ("was this a correction?") and the
    turn picker are the same question, since "no, this isn't a correction" is just one more
    option in the same chip list alongside the candidate turns to roll back to -- no reason to
    make the expert click through a separate yes/no first. routers/expert_workflows.py builds
    the actual candidate list (this module has no graph/turn-history access) and appends that
    "not a correction" option to it right after this call returns, advancing the stage from
    "awaiting_turn_selection_setup" to "awaiting_turn_selection". Picking "not a correction"
    resumes normal processing of the exact same text at the exact same stage, as if this check
    had never fired (see routers/expert_workflows.py's handling of that stage).
    """
    correction = {"original_stage": stage, "original_cursor": cursor,
                  "original_pending": {k: v for k, v in pending.items() if k != "_correction"},
                  "original_text": text}
    reply = "检测到你好像是想修改之前说过的内容，要回退到哪一步重新做？"
    nq = {"target": "correction_turn_pick", "priority": "P0", "question": reply, "chips": None}
    new_state = {"stage": "awaiting_turn_selection_setup", "cursor": cursor,
                  "pending": {**pending, "_correction": correction}}
    return reply, [], nq, new_state


def _build_step_chain(ops: list[dict], from_id: str, clauses: list[str], edge_type: str = "normal",
                       condition: str | None = None, confidence: float = 0.85) -> str:
    """Create one activity node per clause (already extracted -- see _extract_step_clauses),
    chained in sequence and linked from `from_id`. The first edge carries `edge_type`/
    `condition` (e.g. a branch's conditional edge); any edge added between clauses is a plain
    "normal" edge, since sequential clauses still happened on the same path. Returns the id
    of the last node created, i.e. the new cursor.
    """
    prev_id = from_id
    tail_id = from_id
    for i, clause in enumerate(clauses):
        node_id = _nid()
        ops.append({"op": "add_node", "node": {"node_id": node_id, "node_type": "activity",
                                                 "label": clause, "source_turn_ids": [],
                                                 "confidence": confidence, "expert_confirmed": False}})
        edge = {"edge_id": _nid(), "from": prev_id, "to": node_id,
                "edge_type": edge_type if i == 0 else "normal",
                "confidence": confidence, "expert_confirmed": False}
        if i == 0 and condition:
            edge["condition"] = condition
        ops.append({"op": "add_edge", "edge": edge})
        prev_id = node_id
        tail_id = node_id
    return tail_id


def _build_parallel_branches(ops: list[dict], from_id: str, clauses: list[str], edge_type: str = "normal",
                              condition: str | None = None, confidence: float = 0.85) -> str:
    """Build a parallel_split -> one activity node per clause (each linked by a `parallel`
    edge) -> parallel_join structure, for when the expert has confirmed a compound "并/同时"
    sentence really was two things done at the same time. Returns the parallel_join node id,
    i.e. the new cursor (both branches are already merged back into one path by the time the
    caller continues).
    """
    split_id = _nid()
    ops.append({"op": "add_node", "node": {"node_id": split_id, "node_type": "parallel_split",
                                            "label": "并行拆分", "source_turn_ids": [],
                                            "confidence": confidence, "expert_confirmed": False}})
    entry_edge = {"edge_id": _nid(), "from": from_id, "to": split_id, "edge_type": edge_type,
                  "confidence": confidence, "expert_confirmed": False}
    if condition:
        entry_edge["condition"] = condition
    ops.append({"op": "add_edge", "edge": entry_edge})

    branch_tails = []
    for clause in clauses:
        node_id = _nid()
        ops.append({"op": "add_node", "node": {"node_id": node_id, "node_type": "activity",
                                                 "label": clause, "source_turn_ids": [],
                                                 "confidence": confidence, "expert_confirmed": False}})
        ops.append({"op": "add_edge", "edge": {"edge_id": _nid(), "from": split_id, "to": node_id,
                                                "edge_type": "parallel", "confidence": confidence,
                                                "expert_confirmed": False}})
        branch_tails.append(node_id)

    join_id = _nid()
    ops.append({"op": "add_node", "node": {"node_id": join_id, "node_type": "parallel_join",
                                            "label": "并行汇合", "source_turn_ids": [],
                                            "confidence": confidence, "expert_confirmed": False}})
    for t in branch_tails:
        ops.append({"op": "add_edge", "edge": {"edge_id": _nid(), "from": t, "to": join_id,
                                                "edge_type": "parallel", "confidence": confidence,
                                                "expert_confirmed": False}})
    return join_id


def _continue_after_step(resume: str, tail_id: str, pending: dict, ops: list[dict],
                          entry_id: str | None = None) -> tuple[str, list[dict], dict, dict]:
    """What happens after a step's node(s) have been placed on the graph -- the exact same
    logic whether the nodes went straight in (no serial/parallel ambiguity) or only after the
    expert answered the 先后做/同时做 clarifying question (see "compound_parallel_clarify").
    Sharing this one place means the two paths can never quietly drift apart. `entry_id` is
    the cursor value some resume points restore instead of `tail_id` (branch_condition_a and
    parallel_branch_a both keep working from the decision/split node, not the tail of what
    they just recorded, since the *next* turn's answer is a sibling branch off that same
    node, not a continuation of this one).
    """
    if resume == "trigger_detail":
        reply = "明白，我先记下这一步。然后呢？下一步是谁做什么？"
        nq = {"target": "main_path_discovery", "priority": "P0", "question": reply, "chips": None}
        new_state = {"stage": "main_path", "cursor": tail_id, "pending": pending}
        return reply, ops, nq, new_state
    if resume == "main_path":
        reply = "这里是不是只有一种处理方式，还是不同情况下会走不同方向？"
        nq = {"target": "branch_discovery", "priority": "P1", "question": reply,
              "chips": ["只有一种处理方式", "会走不同方向", "不确定，再想想"]}
        new_state = {"stage": "branch_check", "cursor": tail_id, "pending": pending}
        return reply, ops, nq, new_state
    if resume == "branch_condition_a":
        reply = "另一种情况呢？条件是什么，接下来做什么？"
        nq = {"target": "branch_condition_b", "priority": "P1", "question": reply, "chips": None}
        new_state = {"stage": "branch_condition_b", "cursor": entry_id,
                      "pending": {**pending, "branch_a_tail": tail_id}}
        return reply, ops, nq, new_state
    if resume == "branch_condition_b":
        reply = "这两条路径处理完之后，是各自继续，还是要汇总后再进入同一步？"
        nq = {"target": "parallel_merge_discovery", "priority": "P3", "question": reply,
              "chips": ["各自继续", "汇总后再决定", "不确定，再想想"]}
        new_state = {"stage": "merge_check", "cursor": None,
                      "pending": {**pending, "branch_b_tail": tail_id}}
        return reply, ops, nq, new_state
    if resume == "parallel_branch_a":
        reply = "第二项并行的工作呢？"
        nq = {"target": "parallel_merge_discovery", "priority": "P2", "question": reply, "chips": None}
        new_state = {"stage": "parallel_branch_b", "cursor": entry_id,
                      "pending": {**pending, "par_a_tail": tail_id}}
        return reply, ops, nq, new_state
    # resume == "parallel_branch_b"
    a_tail = pending.get("par_a_tail")
    join_id = _nid()
    ops += [
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


def _start_parallel_clarify(resume: str, from_id: str, clauses: list[str], pending: dict, ops: list[dict],
                             edge_type: str = "normal", condition: str | None = None,
                             confidence: float = 0.85) -> tuple[str, list[dict], dict, dict]:
    """Defer step-node creation and ask the expert to disambiguate "先后做" vs "同时做" for a
    compound sentence split on an ambiguous connector (并/并且/同时). The clauses -- already
    extracted from the expert's actual words -- are stashed in `pending`, not re-derived from
    whatever chip text the expert taps next. `ops` is whatever the caller already queued
    before deciding to defer (e.g. trigger_detail's start node) and must still ship this turn.
    """
    compound = {"resume": resume, "from_id": from_id, "clauses": clauses, "edge_type": edge_type,
                "condition": condition, "confidence": confidence}
    joined = "」、「".join(clauses)
    reply = f"这里面「{joined}」，是先后做，还是同时做？"
    nq = {"target": "parallel_merge_discovery", "priority": "P2", "question": reply,
          "chips": ["先后做", "同时做", "不确定，再想想"]}
    new_state = {"stage": "compound_parallel_clarify", "cursor": None,
                  "pending": {**pending, "_compound": compound}}
    return reply, ops, nq, new_state


def _resolve_parallel_clarify(text: str, pending: dict, ops: list[dict]) -> tuple[str, list[dict], dict, dict]:
    compound = pending["_compound"]
    pending = {k: v for k, v in pending.items() if k != "_compound"}
    clauses = compound["clauses"]
    edge_type, condition, confidence = compound["edge_type"], compound["condition"], compound["confidence"]
    if _contains_any(text, ["同时"]):
        tail_id = _build_parallel_branches(ops, compound["from_id"], clauses, edge_type, condition, confidence)
    else:
        # "先后做" or "不确定，再想想": same honest fallback used elsewhere in this file when a
        # tri-state chip answer doesn't clearly say "parallel" -- default to sequential.
        tail_id = _build_step_chain(ops, compound["from_id"], clauses, edge_type, condition, confidence)
    return _continue_after_step(compound["resume"], tail_id, pending, ops, entry_id=compound["from_id"])


def _apply_understanding(resume: str, entry_id: str, understanding: dict, pending: dict, ops: list[dict],
                          edge_type: str = "normal", condition: str | None = None,
                          confidence: float = 0.85) -> tuple[str, list[dict], dict, dict]:
    """Routes a freshly computed `_understand_step` result to the right graph shape --
    shared by all six step-creating stages so this three-way routing exists in exactly one
    place instead of being reimplemented per call site:
    - "ambiguous" -> defer and ask the expert (`_start_parallel_clarify`), same as before.
    - "parallel" -> build the split/branches/join structure directly. The rule-based fallback
      in `_understand_step` never produces this value (regex can only ever say "ambiguous" or
      default to "serial" -- it has no way to be *confident* the expert meant parallel), so
      this branch only ever fires on a real LLM call that was sure enough not to need to ask.
    - anything else ("serial", or a single clause where the question is moot) -> a plain
      sequential chain, same as before.
    """
    clauses = understanding["clauses"]
    relationship = understanding["relationship"]
    if relationship == "ambiguous":
        return _start_parallel_clarify(resume, entry_id, clauses, pending, ops,
                                        edge_type=edge_type, condition=condition, confidence=confidence)
    if relationship == "parallel" and len(clauses) >= 2:
        tail_id = _build_parallel_branches(ops, entry_id, clauses, edge_type, condition, confidence)
    else:
        tail_id = _build_step_chain(ops, entry_id, clauses, edge_type, condition, confidence)
    return _continue_after_step(resume, tail_id, pending, ops, entry_id=entry_id)


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
