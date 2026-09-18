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
        reply = f"好，我先把它理解成一段「{text[:24]}」相关的经历。当时是谁最先发现的？发现后第一件事做什么？"
        nq = {"target": "trigger_discovery", "priority": "P0", "question": reply, "chips": None}
        new_state = {"stage": "trigger_detail", "cursor": None, "pending": {"scenario": text}}
        return reply, ops, nq, new_state

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
        if _contains_any(text, ["会返工", "会"]):
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
        new_state = {"stage": "review", "cursor": None, "pending": {}}
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
