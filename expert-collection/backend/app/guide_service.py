"""Guide Service -- the expert-collection interview engine (PRD 3.2 / 9 / 18). Same call
signature as before: (session_state, expert_text) -> (assistant_reply, graph_ops,
next_question, new_state), plus the current graph and transcript as keyword arguments so the
planner can anchor its questions to what has actually been said.

Architecture (planner + phraser + parser):

1. Parser -- `_understand_step`. Turns one piece of expert free text into step clauses (and,
   when the expert named one, who did each step). Real LLM when the `guide_service` slot is
   configured, the original regex splitter otherwise. Contract unchanged: every clause comes
   from the expert's own words; ambiguous "并/同时" still gets asked about, never guessed.

2. Planner -- this module's stage machine. Deterministic on purpose (reproducible, testable,
   and it keeps "what to ask" out of the 7B model's hands). Compared with the old fixed
   Wizard it:
   - keeps asking "「上一步」之后，下一步是谁做什么？" until the expert says the work is done,
     instead of forcing the branch/parallel/approval questions after exactly two steps;
   - asks for the end condition first, and only then runs structural *sweeps* (branch ->
     parallel -> approval -> retry -> experience). Each sweep's chips are the expert's own
     step labels (PRD 18: options built from what the expert already said are disambiguation,
     not generation), so the answer pins the structure to a concrete step. Sweeps with no
     eligible step are skipped silently;
   - remembers cue phrases the expert used along the way ("如果……", "要主管签字", "返工")
     and opens the matching sweep by quoting them back;
   - cuts upfront background from 7 rounds to 2-3 (起因 -> 目标, skippable -> 限制条件,
     multi-select), since background only exists to serve the process collection.

3. Phraser -- guide_phrasing.finalize. Polishes the template acknowledgement + question into
   natural speech with the LLM, under validation (no invented quotes/numbers, no jargon, one
   question, chip questions never reworded), template fallback on any failure.

Graph edits made by sweeps (inserting a decision/approval node after an existing step,
turning two consecutive steps into simultaneous ones) rewire existing edges with
`update_edge`. The router therefore snapshots the whole graph per turn for rollback instead
of relying only on `source_turn_ids` (see routers/expert_workflows.py).

Correction detection ("哦，我说错了……") still only works with a real LLM -- the rule-based
fallback always reports "not a correction" (IMPLEMENTATION_PLAN.md section 13's decision that
a keyword list does more harm than good there).

Priorities P0-P7 are PRD section 3.2 / 18.2.
"""
from __future__ import annotations

import copy
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from . import graph_ops, guide_phrasing, llm_client, task_layer
from . import settings as app_settings

NODE_TYPE_LABELS = {
    "decision": "判断",
    "parallel_split": "并行拆分",
    "parallel_join": "并行汇合",
    "merge": "汇合",
    "approval": "审批",
}

# --- Chip vocabularies (PRD section 18) --------------------------------------------------

OPENING_CHIPS = ["设备/质量异常", "标准生产工作", "持续改善", "工程/工艺变更"]
GOAL_SKIP_CHIP = "先跳过，直接讲怎么做的"
CONSTRAINT_CHIPS = ["时间紧", "安全风险", "缺备件/物料", "需要跨部门协调", "无"]
CONSTRAINT_FOLLOWUPS = {
    "时间紧": "当时给的时间窗口大概多久？",
    "安全风险": "具体是什么安全风险？",
    "缺备件/物料": "具体缺什么，大概什么时候能到？",
    "需要跨部门协调": "需要协调哪些部门？",
}
END_CHIP = "后面就处理完了"
NO_BRANCH_CHIP = "没有，一直是这么处理"
NO_PARALLEL_CHIP = "没有，都是一件做完再做下一件"
NO_APPROVAL_CHIP = "没有需要等人确认的"
NO_RETRY_CHIP = "没有返工的情况"
REJOIN_END_CHIP = "到这里整件事就结束了"
EXPERIENCE_NONE_CHIP = "没有特别靠经验的地方"
EXPERIENCE_MIXED_CHIP = "规定和经验都有，说不清"
PARALLEL_CLARIFY_CHIPS = ["先后做", "同时做", "不确定，再想想"]

SWEEP_ORDER = ["branch", "parallel", "approval", "retry", "experience"]
MAX_STEP_CHIPS = 8
_CHIP_LABEL_MAX = 16

REVIEW_TEXT = ("两张图都整理好了：「任务协作」看谁负责哪一段、怎么交接，「SOP 步骤」看每一步具体怎么做。"
               "请在右边切换着从头到尾看一遍：有不对的地方直接告诉我，没问题就点「确认并提交」。")
REVIEW_REPEAT_TEXT = "已经在最终确认阶段了——有需要修改的地方，直接说，我来改图；没问题的话可以点「确认并提交」。"


@dataclass
class _Out:
    """One planner decision: template ack, graph ops, next question (None = final review),
    new state, and the closing line used only when there is no next question."""
    ack: str
    ops: list[dict]
    nq: dict | None
    state: dict[str, Any]
    closing: str | None = None
    extra: dict = field(default_factory=dict)


# --- Public API ---------------------------------------------------------------------------

def initial_state() -> dict[str, Any]:
    return {"stage": "opening", "cursor": None, "pending": {}}


def initial_turn() -> tuple[str, dict[str, Any]]:
    ack = "你好！我会把你讲的真实经历整理成一张流程图，你只管讲，不用自己画。"
    question = "先回忆一件你亲自处理过、印象比较深的事，大概属于哪一类？"
    next_question = {
        "target": "trigger_discovery", "priority": "P0", "question": question,
        "chips": OPENING_CHIPS, "ack": ack, "why": guide_phrasing.WHY_BY_TARGET["trigger_discovery"],
    }
    return ack + question, next_question


def handle_turn(state: dict[str, Any], text: str, turn_id: str | None = None,
                skip_correction_check: bool = False, graph: dict | None = None,
                history: list[dict] | None = None,
                ) -> tuple[str, list[dict], dict | None, dict[str, Any]]:
    """Returns (assistant_reply, graph_ops, next_question_or_None, new_state).

    `graph` is the workflow's graph *before* this turn (read-only here -- ops are returned,
    not applied). `history` is the transcript before this turn, used only for phrasing.
    `turn_id` is stamped onto every add_node/add_edge op's `source_turn_ids`.
    `skip_correction_check` is set by the router when re-processing text after the expert
    answered "不是，这是新的一步" to the correction picker, so the same text can't loop.
    """
    graph = graph if graph is not None else graph_ops.new_graph()
    out = _dispatch_turn(state, text.strip(), graph, skip_correction_check)
    if turn_id:
        for op in out.ops:
            if op.get("op") == "add_node":
                op["node"]["source_turn_ids"] = [turn_id]
            elif op.get("op") == "add_edge":
                op["edge"]["source_turn_ids"] = [turn_id]
    labels = [n["label"] for n in _preview(graph, out.ops)["nodes"]]
    reply, nq = guide_phrasing.finalize(out.ack, out.nq, last_expert_message=text.strip(),
                                        history=history, known_labels=labels, closing_text=out.closing)
    return reply, out.ops, nq, out.state


# Which sweep a mid-sweep stage belongs to (used when the graph is refreshed mid-answer).
_SWEEP_KIND_BY_STAGE = {
    "sweep_branch_pick": "branch", "branch_cond_a": "branch", "branch_cond_b": "branch",
    "branch_b_steps": "branch", "branch_b_rejoin": "branch",
    "sweep_parallel_pick": "parallel",
    "sweep_approval_pick": "approval", "approval_who": "approval",
    "sweep_retry_pick": "retry", "retry_target": "retry",
    "experience": "experience", "experience_detail": "experience",
}


def state_after_regeneration(state: dict[str, Any], graph: dict) -> tuple[str, dict | None, dict[str, Any]]:
    """Reset the interview after the whole graph was replaced by 「刷新工作流图」.

    Every node id the old state pointed at (cursor, sweep chip options, pending branch /
    compound / correction scratch) belongs to the discarded graph, so none of it may survive.
    The regenerated graph always passed validation (it has a start and an end), so instead of
    starting the interview over, continue from the structural sweeps on the *new* graph --
    their chips are rebuilt from the new step labels. Sweeps the expert already answered
    before the refresh aren't asked again; if none are left, go straight to final review.
    Background (case_context), cue memory and the chosen category are kept.

    Returns (assistant_reply, next_question_or_None, new_state).
    """
    pending = state.get("pending", {})
    kept = {k: v for k, v in pending.items() if k in ("case_context", "category", "cues", "sweeps_done")}
    # A sweep counts as "done" as soon as it is asked. One that was still mid-answer when the
    # graph was refreshed never got its answer applied to the new graph -- ask it again.
    in_flight = _SWEEP_KIND_BY_STAGE.get(state.get("stage", ""))
    if in_flight:
        kept["sweeps_done"] = [k for k in kept.get("sweeps_done", []) if k != in_flight]
    out = _next_sweep("流程图已经按整段对话重新整理好了，我们在新图的基础上接着确认几处细节。", kept, [], graph)
    if out.nq is None:
        out.ack = "流程图已经按整段对话重新整理好了。"
    labels = [n["label"] for n in graph.get("nodes", [])]
    reply, nq = guide_phrasing.finalize(out.ack, out.nq, last_expert_message="",
                                        known_labels=labels, closing_text=out.closing)
    return reply, nq, out.state


def progress(state: dict[str, Any], graph: dict) -> float:
    """Plain, explainable completion estimate shown to the expert: background ~15%, the
    step-by-step narration up to 60%, then each structural sweep, 100% at final review."""
    stage = state.get("stage", "opening")
    background = {"opening": 0.0, "scenario_trigger": 0.05, "scenario_goal": 0.1,
                  "context_constraints": 0.12, "context_constraints_clarify": 0.14, "trigger_detail": 0.15}
    if stage in background:
        return background[stage]
    if stage == "review":
        return 1.0
    steps = sum(1 for n in graph.get("nodes", []) if n["node_type"] == "activity")
    if not graph.get("end_node_ids"):
        return round(min(0.6, 0.2 + 0.05 * steps), 2)
    done = len(state.get("pending", {}).get("sweeps_done", []))
    return round(min(0.95, 0.65 + 0.06 * done), 2)


# --- Dispatch -----------------------------------------------------------------------------

# Stages from the previous fixed-Wizard version that no longer exist. A workflow saved
# mid-conversation under the old flow is migrated on its next turn instead of getting stuck.
_LEGACY_BACKGROUND_FIELDS = {
    "scenario_success": "scenario_success",
    "context_known": "known_info", "context_known_clarify": "known_info",
    "context_unknown": "unknown_info", "context_unknown_clarify": "unknown_info",
    "context_resources": "available_resources", "context_resources_clarify": "available_resources",
}
_LEGACY_STRUCTURAL_STAGES = {
    "branch_check", "branch_condition_a", "branch_condition_b", "merge_check",
    "parallel_check", "parallel_branch_a", "parallel_branch_b", "approval_check", "retry_check",
}


def _dispatch_turn(state: dict[str, Any], text: str, graph: dict, skip_correction_check: bool) -> _Out:
    stage = state["stage"]
    cursor = state.get("cursor")
    pending = state.get("pending", {})
    ops: list[dict] = []

    if stage in _LEGACY_BACKGROUND_FIELDS:
        pending = _case_context_set(pending, _LEGACY_BACKGROUND_FIELDS[stage], text)
        return _ask_first_step("好，背景信息记下了。", pending, ops)
    if stage in _LEGACY_STRUCTURAL_STAGES:
        return _legacy_structural(graph, cursor, pending)

    if stage == "opening":
        return _handle_opening(text, pending)
    if stage == "scenario_trigger":
        pending = _case_context_set(pending, "scenario_trigger", text)
        clause = _first_clause(text)
        ack = f"了解，起因是「{clause}」。" if clause else "了解了事情的起因。"
        return _ask_goal(ack, pending)
    if stage == "scenario_goal":
        if text.startswith("先跳过") or _is_negative(text):
            pending = _case_context_mark_skipped(pending, "scenario_goal")
            ack = "好，目标先不展开。"
        else:
            pending = _case_context_set(pending, "scenario_goal", text)
            clause = _first_clause(text)
            ack = f"目标是「{clause}」，记下了。" if clause else "目标记下了。"
        return _ask_constraints(ack, pending)
    if stage == "context_constraints":
        return _handle_constraints_select(text, pending)
    if stage == "context_constraints_clarify":
        selected = pending.get("_b_selected", [])
        combined = f"{'、'.join(selected)}：{text}" if selected else text
        pending = _case_context_set(pending, "constraints", combined)
        pending = {k: v for k, v in pending.items() if k != "_b_selected"}
        return _ask_first_step("这些限制记下了。", pending, ops)

    if stage == "compound_parallel_clarify":
        return _resolve_parallel_clarify(text, pending, ops, graph)

    if stage == "trigger_detail":
        understanding = _understand(text, skip_correction_check)
        if understanding.get("is_correction"):
            return _start_correction_pick(stage, cursor, pending, text)
        pending = _record_cues(pending, text)
        start_id = _nid()
        ops += [
            {"op": "add_node", "node": _node(start_id, "start", "开始", 0.9)},
            {"op": "set_start", "node_id": start_id},
        ]
        return _apply_understanding("main_path", start_id, understanding, pending, ops, graph, confidence=0.9)

    if stage == "main_path":
        if _is_end_signal(text):
            return _ask_end_condition("好，主要步骤讲完了。", cursor, pending, ops)
        understanding = _understand(text, skip_correction_check)
        if understanding.get("is_correction"):
            return _start_correction_pick(stage, cursor, pending, text)
        pending = _record_cues(pending, text)
        return _apply_understanding("main_path", cursor, understanding, pending, ops, graph)

    if stage == "end_condition":
        return _handle_end_condition(text, cursor, pending, ops, graph)

    if stage == "sweep_branch_pick":
        return _handle_branch_pick(text, pending, ops, graph)
    if stage == "branch_cond_a":
        return _handle_branch_cond_a(text, pending, ops, graph)
    if stage == "branch_cond_b":
        return _handle_branch_cond_b(text, pending, ops, graph)
    if stage == "branch_b_steps":
        understanding = _understand(text, skip_correction_check)
        if understanding.get("is_correction"):
            return _start_correction_pick(stage, cursor, pending, text)
        br = pending["_branch"]
        return _apply_understanding("branch_b", br["decision"], understanding, pending, ops, graph,
                                    edge_type="conditional", condition=br.get("cond_b"), confidence=0.8)
    if stage == "branch_b_rejoin":
        return _handle_branch_rejoin(text, cursor, pending, ops, graph)
    if stage == "sweep_parallel_pick":
        return _handle_parallel_pick(text, pending, ops, graph)
    if stage == "sweep_approval_pick":
        return _handle_approval_pick(text, pending, ops, graph)
    if stage == "approval_who":
        return _handle_approval_who(text, cursor, pending, ops, graph)
    if stage == "sweep_retry_pick":
        return _handle_retry_pick(text, pending, ops, graph)
    if stage == "retry_target":
        return _handle_retry_target(text, cursor, pending, ops, graph)
    if stage == "experience":
        return _handle_experience(text, pending, ops, graph)
    if stage == "experience_detail":
        pending = _case_context_set(pending, "experience_notes", text)
        return _to_review("这条经验很有价值，已经记下了。", pending, ops)

    if stage == "task_outline":
        return _handle_task_outline(text, pending, ops, graph)
    if stage == "task_boundary":
        return _handle_task_boundary(text, pending, ops, graph)

    # stage == "review" or unknown: nothing more to structurally extract
    return _Out("", ops, None, state, closing=REVIEW_REPEAT_TEXT)


# --- Background (Scenario + Case Context, trimmed) ----------------------------------------

def _handle_opening(text: str, pending: dict) -> _Out:
    pending = {**pending, "category": text}
    if text in OPENING_CHIPS:
        ack = f"好，那就讲一次「{text}」的经历。"
    elif len(text) > 15:
        # The expert went straight into the story -- that *is* the trigger answer, don't ask
        # "what happened" a second time.
        pending = _case_context_set(pending, "scenario_trigger", text)
        return _ask_goal("好，事情的起因我先记下了。", pending)
    else:
        ack = "好，就讲这件事。"
    nq = _q("scenario_discovery", "P0", "当时具体发生了什么，是怎么发现的？")
    return _Out(ack, [], nq, _st("scenario_trigger", None, pending))


def _ask_goal(ack: str, pending: dict) -> _Out:
    nq = _q("scenario_discovery", "P0", "处理这件事，你当时最想达成的目标是什么？", chips=[GOAL_SKIP_CHIP])
    return _Out(ack, [], nq, _st("scenario_goal", None, pending))


def _ask_constraints(ack: str, pending: dict) -> _Out:
    nq = _q("case_context_discovery", "P1", "当时有没有什么限制，让这件事更难办？（可多选）",
            chips=CONSTRAINT_CHIPS, chip_mode="multi_select")
    return _Out(ack, [], nq, _st("context_constraints", None, pending))


def _handle_constraints_select(text: str, pending: dict) -> _Out:
    selected = _multiselect(text)
    if not selected or selected == ["无"] or _is_negative(text):
        pending = _case_context_mark_skipped(pending, "constraints")
        return _ask_first_step("好，没有特别的限制。", pending, [])
    pending = {**pending, "_b_selected": selected}
    if len(selected) == 1 and selected[0] in CONSTRAINT_FOLLOWUPS:
        question = CONSTRAINT_FOLLOWUPS[selected[0]]
    else:
        # One merged question instead of several followups glued together with "；" --
        # PRD 3.2 rule 4: one question per turn.
        quoted = "".join(f"「{s}」" for s in selected)
        question = f"你提到{quoted}，具体是什么情况？"
    return _Out("", [], _q("case_context_discovery", "P1", question), _st("context_constraints_clarify", None, pending))


def _ask_first_step(ack: str, pending: dict, ops: list[dict]) -> _Out:
    nq = _q("main_path_discovery", "P0", "我们按时间顺序捋一遍：发现问题之后，第一件事是谁做了什么？")
    return _Out(ack, ops, nq, _st("trigger_detail", None, pending))


# --- Main path ----------------------------------------------------------------------------

_END_SIGNAL_RE = re.compile(
    r"^(没有了|没了|就这些|就这样|结束了?|完了|处理完了?|后面没有了|后面就处理完了|到这里就?结束了?|就处理完了|没有下一步了?)[。！!.]?$"
)


def _is_end_signal(text: str) -> bool:
    return text == END_CHIP or bool(_END_SIGNAL_RE.match(text.strip()))


def _ask_end_condition(ack: str, cursor: str | None, pending: dict, ops: list[dict]) -> _Out:
    nq = _q("end_condition_discovery", "P0", "那整件事做到什么程度，才算处理完了？")
    return _Out(ack, ops, nq, _st("end_condition", cursor, pending))


def _handle_end_condition(text: str, cursor: str | None, pending: dict, ops: list[dict], graph: dict) -> _Out:
    end_id = _nid()
    label = _strip_filler(text)[:40] or "结束"
    ops += [{"op": "add_node", "node": _node(end_id, "end", label, 0.9)}]
    if cursor:
        ops.append({"op": "add_edge", "edge": _edge(cursor, end_id, "normal", 0.9)})
    ops.append({"op": "set_end", "node_id": end_id})
    # Drop stage scratch state from before; case_context and cue memory stay.
    kept = {k: v for k, v in pending.items() if k in ("case_context", "category", "cues")}
    return _next_sweep("结束的标志记下了，主要流程已经连起来了。", kept, ops, graph)


# --- Structural sweeps --------------------------------------------------------------------

def _next_sweep(ack: str, pending: dict, ops: list[dict], graph: dict) -> _Out:
    preview = _preview(graph, ops)
    done = list(pending.get("sweeps_done", []))
    builders = {"branch": _build_branch_sweep, "parallel": _build_parallel_sweep,
                "approval": _build_approval_sweep, "retry": _build_retry_sweep,
                "experience": _build_experience_sweep}
    pending = {k: v for k, v in pending.items() if k not in ("_options", "_reasked", "_branch")}
    for kind in SWEEP_ORDER:
        if kind in done:
            continue
        done.append(kind)
        pending = {**pending, "sweeps_done": list(done)}
        result = builders[kind](ack, preview, pending, ops)
        if result is not None:
            return result
    return _to_review(ack, pending, ops)


def _to_review(ack: str, pending: dict, ops: list[dict]) -> _Out:
    """Every path that finishes the step (SOP) graph ends here. Before final review, the expert
    defines the task layer (IMPLEMENTATION_PLAN.md section 18) -- unless it already exists,
    e.g. the expert is mid-review. A graph refresh drops `task_workflow` from pending (its
    sop_node_ids pointed at the discarded graph), so the task question is asked again then.
    """
    if not pending.get("task_workflow"):
        kept = {k: v for k, v in pending.items() if k in ("case_context", "sweeps_done", "category")}
        nq = _q("task_outline_discovery", "P0", task_layer.TASK_OUTLINE_QUESTION,
                chips=[task_layer.SINGLE_TASK_CHIP])
        return _Out(ack, ops, nq, _st("task_outline", None, kept))
    kept = {k: v for k, v in pending.items() if k in ("case_context", "sweeps_done", "task_workflow")}
    return _Out(ack, ops, None, _st("review", None, kept), closing=REVIEW_TEXT)


# --- Task layer (IMPLEMENTATION_PLAN.md section 18) ------------------------------------------
# The expert defines the task-collaboration DAG directly (priority-1 source); the LLM only
# structures the outline (task_layer.parse_outline). Boundaries are the expert's own picks
# among already-described steps, in graph (topological) order -- never guessed.

def _handle_task_outline(text: str, pending: dict, ops: list[dict], graph: dict) -> _Out:
    g = _preview(graph, ops)
    if text.startswith(task_layer.SINGLE_TASK_CHIP):
        # Single-task name = the expert's own opening answer, never a made-up summary.
        items, structured_by = [{"name": (pending.get("category") or "整体任务")[:40], "owner": None}], "rule"
    else:
        items, structured_by = task_layer.parse_outline(text)
    items = items or [{"name": text[:40], "owner": None}]
    if len(items) == 1:
        return _finish_task_layer(pending, ops, g, items, [None], structured_by)
    pending = {**pending, "_task_items": items, "_task_starts": [None], "_task_structured_by": structured_by}
    return _ask_task_boundary("好，按这几个任务来分。", pending, ops, g)


def _ask_task_boundary(ack: str, pending: dict, ops: list[dict], g: dict) -> _Out:
    """Ask where task `len(starts)` begins. Only steps after the last real start so far are
    offered, which keeps tasks contiguous and in the order the expert listed them."""
    items, starts = pending["_task_items"], pending["_task_starts"]
    options: dict[str, str | None] = dict(task_layer.step_candidates(g, [s for s in starts if s]))
    options[task_layer.NO_STEP_CHIP] = None
    nq = _q("task_boundary_discovery", "P0", task_layer.boundary_question(items, len(starts)), chips=list(options))
    return _Out(ack, ops, nq, _st("task_boundary", None, {**pending, "_boundary_options": options}))


def _handle_task_boundary(text: str, pending: dict, ops: list[dict], graph: dict) -> _Out:
    g = _preview(graph, ops)
    options = pending.get("_boundary_options", {})
    if text not in options:
        # Same honest re-ask as the sweeps: matching free text to a step would be guessing.
        return _ask_task_boundary("麻烦从下面列出的步骤里选一个，我才知道这个任务从哪里开始。", pending, ops, g)
    starts = pending["_task_starts"] + [options[text]]
    pending = {**pending, "_task_starts": starts}
    if len(starts) < len(pending["_task_items"]):
        return _ask_task_boundary("", pending, ops, g)
    return _finish_task_layer(pending, ops, g, pending["_task_items"], starts,
                              pending.get("_task_structured_by", "rule"))


def _finish_task_layer(pending: dict, ops: list[dict], g: dict, items: list[dict],
                       starts: list[str | None], structured_by: str) -> _Out:
    task_workflow = task_layer.build_task_workflow(g, items, starts, structured_by)
    pending = {k: v for k, v in pending.items() if not k.startswith("_task") and k != "_boundary_options"}
    return _to_review("任务划分记下了。", {**pending, "task_workflow": task_workflow}, ops)


def _cue_prefix(pending: dict, kind: str) -> str:
    cue = pending.get("cues", {}).get(kind)
    return f"你前面提到「{cue}」。" if cue else ""


def _build_branch_sweep(ack: str, g: dict, pending: dict, ops: list[dict]) -> _Out | None:
    candidates = [n for n in _activities(g)
                  if len(_out_edges(g, n["node_id"])) == 1
                  and _out_edges(g, n["node_id"])[0]["edge_type"] == "normal"]
    if not candidates:
        return None
    options = _make_options(candidates)
    question = _cue_prefix(pending, "branch") + "回头看整个过程，有没有哪一步之后，会因为情况不同而处理不一样？"
    nq = _q("branch_discovery", "P1", question, chips=[*options, NO_BRANCH_CHIP])
    return _Out(ack, ops, nq, _st("sweep_branch_pick", None, {**pending, "_options": options}))


def _handle_branch_pick(text: str, pending: dict, ops: list[dict], graph: dict) -> _Out:
    picked = _pick(text, pending, graph)
    if picked == "unmatched":
        return _reask(pending, ops, graph, "sweep_branch_pick")
    if picked is None:
        return _next_sweep("好，没有需要分情况处理的地方。", pending, ops, graph)
    edge = _out_edges(graph, picked)[0]
    succ = _get_node(graph, edge["to"])
    decision_id = _nid()
    ops += [
        {"op": "add_node", "node": {**_node(decision_id, "decision", "判断", 0.8),
                                     "decision_question": f"「{_get_node(graph, picked)['label']}」之后走哪种处理？"}},
        {"op": "add_edge", "edge": _edge(picked, decision_id, "normal", 0.8)},
        {"op": "update_edge", "edge_id": edge["edge_id"], "patch": {"from": decision_id, "edge_type": "conditional"}},
    ]
    n_label = _get_node(graph, picked)["label"]
    if succ["node_type"] == "end":
        question = f"在「{n_label}」之后，什么情况下就按正常流程结束了？"
    else:
        question = f"在「{n_label}」之后，什么情况下会接着做「{succ['label']}」？"
    branch = {"decision": decision_id, "edge_a": edge["edge_id"], "n": picked, "s": succ["node_id"]}
    pending = {**{k: v for k, v in pending.items() if k not in ("_options", "_reasked")}, "_branch": branch}
    return _Out("", ops, _q("branch_condition", "P1", question), _st("branch_cond_a", None, pending))


def _handle_branch_cond_a(text: str, pending: dict, ops: list[dict], graph: dict) -> _Out:
    br = pending["_branch"]
    condition = _strip_filler(text)[:40]
    ops.append({"op": "update_edge", "edge_id": br["edge_a"], "patch": {"condition": condition}})
    nq = _q("branch_condition", "P1", "那在其他情况下，条件是什么、会怎么处理？")
    return _Out(f"好，「{condition}」时按原来的做法走。", ops, nq, _st("branch_cond_b", None, pending))


def _handle_branch_cond_b(text: str, pending: dict, ops: list[dict], graph: dict) -> _Out:
    br = pending["_branch"]
    condition, rest = _split_condition(text)
    if not rest:
        pending = {**pending, "_branch": {**br, "cond_b": condition[:40]}}
        nq = _q("branch_condition", "P1", "这种情况下，具体会做什么？")
        return _Out(f"条件是「{condition[:40]}」，记下了。", ops, nq, _st("branch_b_steps", None, pending))
    understanding = _understand_step(rest)
    pending = {**pending, "_branch": {**br, "cond_b": condition[:40]}}
    return _apply_understanding("branch_b", br["decision"], understanding, pending, ops, graph,
                                edge_type="conditional", condition=condition[:40], confidence=0.8)


def _ask_branch_rejoin(ack: str, tail_id: str, pending: dict, ops: list[dict], graph: dict) -> _Out:
    g = _preview(graph, ops)
    br = pending["_branch"]
    downstream = [n for n in _downstream(g, br["s"]) if n["node_type"] == "activity"]
    options = _make_options(downstream[:MAX_STEP_CHIPS])
    nq = _q("branch_rejoin", "P3", "这种情况处理完之后，接下来做哪一步？", chips=[*options, REJOIN_END_CHIP])
    return _Out(ack, ops, nq, _st("branch_b_rejoin", tail_id, {**pending, "_options": options}))


def _handle_branch_rejoin(text: str, cursor: str, pending: dict, ops: list[dict], graph: dict) -> _Out:
    options = pending.get("_options", {})
    target = None
    if text == REJOIN_END_CHIP or _is_end_signal(text) or _is_negative(text):
        target = (graph.get("end_node_ids") or [None])[0]
    elif text in options:
        target = options[text]
    else:
        by_label = _node_id_by_label(graph, text)
        if by_label and by_label in options.values():
            target = by_label
    if target:
        ops.append({"op": "add_edge", "edge": _edge(cursor, target, "normal", 0.8)})
        return _next_sweep("好，这种情况也接回来了。", pending, ops, graph)
    # Anything else is read as "there are more steps in this case" -- record them and ask
    # again, so a multi-step exception path works without a separate question per step.
    understanding = _understand_step(text)
    return _apply_understanding("branch_b", cursor, understanding, pending, ops, graph, confidence=0.8)


def _build_parallel_sweep(ack: str, g: dict, pending: dict, ops: list[dict]) -> _Out | None:
    options: dict[str, str] = {}
    for x in _activities(g):
        inc = _in_edges(g, x["node_id"])
        if len(inc) != 1 or inc[0]["edge_type"] != "normal":
            continue
        p = _get_node(g, inc[0]["from"])
        if not p or p["node_type"] != "activity" or len(_out_edges(g, p["node_id"])) != 1:
            continue
        chip = f"「{_short(p['label'])}」和「{_short(x['label'])}」"
        options.setdefault(chip, f"{p['node_id']}|{x['node_id']}")
        if len(options) >= MAX_STEP_CHIPS:
            break
    if not options:
        return None
    nq = _q("parallel_discovery", "P2", "有没有哪两件事，其实是同时进行的，不用等一件做完再做另一件？",
            chips=[*options, NO_PARALLEL_CHIP])
    return _Out(ack, ops, nq, _st("sweep_parallel_pick", None, {**pending, "_options": options}))


def _handle_parallel_pick(text: str, pending: dict, ops: list[dict], graph: dict) -> _Out:
    options = pending.get("_options", {})
    if text not in options:
        if _is_negative(text) or text == NO_PARALLEL_CHIP:
            return _next_sweep("好，都是一件做完再做下一件。", pending, ops, graph)
        return _reask(pending, ops, graph, "sweep_parallel_pick")
    p_id, x_id = options[text].split("|")
    split_id, join_id = _nid(), _nid()
    ops += [
        {"op": "add_node", "node": _node(split_id, "parallel_split", "并行拆分", 0.8)},
        {"op": "add_node", "node": _node(join_id, "parallel_join", "并行汇合", 0.8)},
    ]
    for e in _in_edges(graph, p_id):
        ops.append({"op": "update_edge", "edge_id": e["edge_id"], "patch": {"to": split_id}})
    for e in _out_edges(graph, p_id):  # the single P -> X edge
        ops.append({"op": "remove_edge", "edge_id": e["edge_id"]})
    for e in _out_edges(graph, x_id):
        ops.append({"op": "update_edge", "edge_id": e["edge_id"], "patch": {"from": join_id}})
    ops += [
        {"op": "add_edge", "edge": _edge(split_id, p_id, "parallel", 0.8)},
        {"op": "add_edge", "edge": _edge(split_id, x_id, "parallel", 0.8)},
        {"op": "add_edge", "edge": _edge(p_id, join_id, "parallel", 0.8)},
        {"op": "add_edge", "edge": _edge(x_id, join_id, "parallel", 0.8)},
    ]
    return _next_sweep(f"好，{text}改成同时进行。", pending, ops, graph)


def _build_approval_sweep(ack: str, g: dict, pending: dict, ops: list[dict]) -> _Out | None:
    if any(n["node_type"] == "approval" for n in g["nodes"]):
        return None
    candidates = [n for n in _activities(g) if _out_edges(g, n["node_id"])]
    if not candidates:
        return None
    options = _make_options(candidates[:MAX_STEP_CHIPS])
    question = _cue_prefix(pending, "approval") + "这些步骤里，有没有哪一步做完之后，要等人确认或批准才能继续？"
    nq = _q("approval_discovery", "P4", question, chips=[*options, NO_APPROVAL_CHIP])
    return _Out(ack, ops, nq, _st("sweep_approval_pick", None, {**pending, "_options": options}))


def _handle_approval_pick(text: str, pending: dict, ops: list[dict], graph: dict) -> _Out:
    picked = _pick(text, pending, graph)
    if picked == "unmatched":
        return _reask(pending, ops, graph, "sweep_approval_pick")
    if picked is None:
        return _next_sweep("好，不需要等人确认。", pending, ops, graph)
    approval_id = _nid()
    ops.append({"op": "add_node", "node": _node(approval_id, "approval", "审批", 0.8)})
    for e in _out_edges(graph, picked):
        ops.append({"op": "update_edge", "edge_id": e["edge_id"], "patch": {"from": approval_id}})
    ops.append({"op": "add_edge", "edge": _edge(picked, approval_id, "approval", 0.8)})
    # PRD 18.3: "是否需要确认" was the structural question (chips); "谁确认" is recall -- its
    # own open question, no chips.
    nq = _q("approval_who", "P4", "是谁来确认或批准？")
    pending = {k: v for k, v in pending.items() if k not in ("_options", "_reasked")}
    return _Out(f"「{_get_node(graph, picked)['label']}」之后要等人确认。", ops, nq,
                _st("approval_who", approval_id, pending))


def _handle_approval_who(text: str, cursor: str, pending: dict, ops: list[dict], graph: dict) -> _Out:
    who = _strip_filler(text)[:20]
    ops.append({"op": "update_node", "node_id": cursor,
                "patch": {"actor_roles": [who], "label": f"审批（{who}）"}})
    ack = f"记下了，由「{who}」确认。"
    if not graph.get("end_node_ids"):  # legacy (pre-sweep) session: the end isn't recorded yet
        return _ask_end_condition(ack, cursor, pending, ops)
    return _next_sweep(ack, pending, ops, graph)


def _build_retry_sweep(ack: str, g: dict, pending: dict, ops: list[dict]) -> _Out | None:
    candidates = [n for n in _activities(g) if not (n.get("retry_semantics") or {}).get("enabled")]
    if not candidates:
        return None
    options = _make_options(candidates[:MAX_STEP_CHIPS])
    question = _cue_prefix(pending, "retry") + "有没有哪一步，如果结果不合格，就要回到前面重新做？"
    nq = _q("retry_discovery", "P5", question, chips=[*options, NO_RETRY_CHIP])
    return _Out(ack, ops, nq, _st("sweep_retry_pick", None, {**pending, "_options": options}))


def _handle_retry_pick(text: str, pending: dict, ops: list[dict], graph: dict) -> _Out:
    picked = _pick(text, pending, graph)
    if picked == "unmatched":
        return _reask(pending, ops, graph, "sweep_retry_pick")
    if picked is None:
        return _next_sweep("好，没有返工的情况。", pending, ops, graph)
    g = _preview(graph, ops)
    targets = [n for n in _ancestors(g, picked) if n["node_type"] == "activity"]
    options = _make_options([_get_node(g, picked), *targets][:MAX_STEP_CHIPS])
    nq = _q("retry_target", "P5", "不合格的话，要回到哪一步重新做？", chips=list(options))
    pending = {**{k: v for k, v in pending.items() if k != "_reasked"}, "_options": options}
    return _Out(f"「{_get_node(graph, picked)['label']}」不合格时会返工。", ops, nq,
                _st("retry_target", picked, pending))


def _handle_retry_target(text: str, cursor: str, pending: dict, ops: list[dict], graph: dict) -> _Out:
    options = pending.get("_options") or {}
    target = options.get(text)
    if target is None and _node_id_by_label(graph, text) in options.values():
        target = _node_id_by_label(graph, text)
    retry = {"enabled": True, "rework_reference_node_id": target, "condition": "结果不合格",
             "description": None if target else text[:60]}
    ops.append({"op": "set_retry_semantics", "node_id": cursor, "retry_semantics": retry})
    if target:
        ack = f"好，不合格时回到「{_get_node(graph, target)['label']}」重做。"
    else:
        ack = "返工的说明记下了，提交前可以在图上再确认一下是哪一步。"
    if not graph.get("end_node_ids"):  # legacy (pre-sweep) session
        return _ask_end_condition(ack, cursor, {k: v for k, v in pending.items() if k != "_options"}, ops)
    return _next_sweep(ack, pending, ops, graph)


def _build_experience_sweep(ack: str, g: dict, pending: dict, ops: list[dict]) -> _Out | None:
    # PRD 18.2 P6: no "标准/经验" main options (forcing a binary hides mixed cases) -- only
    # fallback chips, so the expert has to describe it in their own words.
    nq = _q("experience_discovery", "P6", "整个过程中，有没有哪个判断主要靠经验，而不是照规定做的？",
            chips=[EXPERIENCE_NONE_CHIP, EXPERIENCE_MIXED_CHIP])
    return _Out(ack, ops, nq, _st("experience", None, pending))


def _handle_experience(text: str, pending: dict, ops: list[dict], graph: dict) -> _Out:
    if text == EXPERIENCE_NONE_CHIP or _is_negative(text):
        return _to_review("好。", pending, ops)
    if text == EXPERIENCE_MIXED_CHIP:
        nq = _q("experience_discovery", "P6", "能举个例子吗：当时哪部分是照规定、哪部分是靠经验判断的？")
        return _Out("", ops, nq, _st("experience_detail", None, pending))
    pending = _case_context_set(pending, "experience_notes", text)
    return _to_review("这条经验很有价值，已经记下了。", pending, ops)


def _pick(text: str, pending: dict, graph: dict) -> str | None:
    """Resolve a sweep answer to a node id. None = the expert said "no"; "unmatched" = free
    text that names neither an option nor a step (re-asked once, then skipped)."""
    options = pending.get("_options", {})
    if text in options:
        return options[text]
    by_label = _node_id_by_label(graph, text)
    if by_label and by_label in options.values():
        return by_label
    if _is_negative(text) or text in (NO_BRANCH_CHIP, NO_APPROVAL_CHIP, NO_RETRY_CHIP):
        return None
    return "unmatched"


def _reask(pending: dict, ops: list[dict], graph: dict, stage: str) -> _Out:
    if pending.get("_reasked"):
        return _next_sweep("好，这个先跳过，提交前可以在图上再改。", pending, ops, graph)
    options = pending.get("_options", {})
    none_chip = {"sweep_branch_pick": NO_BRANCH_CHIP, "sweep_parallel_pick": NO_PARALLEL_CHIP,
                 "sweep_approval_pick": NO_APPROVAL_CHIP, "sweep_retry_pick": NO_RETRY_CHIP}[stage]
    target = {"sweep_branch_pick": "branch_discovery", "sweep_parallel_pick": "parallel_discovery",
              "sweep_approval_pick": "approval_discovery", "sweep_retry_pick": "retry_discovery"}[stage]
    nq = _q(target, "P1", "我没对上是哪一步——麻烦从下面选一下，没有的话选最后一项。", chips=[*options, none_chip])
    return _Out("", ops, nq, _st(stage, None, {**pending, "_reasked": True}))


def _legacy_structural(graph: dict, cursor: str | None, pending: dict) -> _Out:
    """A session saved mid-way through the old fixed Wizard's structural questions: continue
    in the new flow from wherever the graph actually is."""
    ops: list[dict] = []
    kept = {k: v for k, v in pending.items() if k in ("case_context", "category")}
    ack = "我们换个方式接着梳理。"
    if graph.get("end_node_ids"):
        return _next_sweep(ack, kept, ops, graph)
    tails = [n for n in graph["nodes"] if n["node_type"] not in ("end",) and not _out_edges(graph, n["node_id"])]
    tail = tails[-1]["node_id"] if tails else cursor
    return _ask_end_condition(ack, tail, kept, ops)


# --- Step placement -------------------------------------------------------------------------

def _apply_understanding(resume: str, entry_id: str, understanding: dict, pending: dict, ops: list[dict],
                         graph: dict, edge_type: str = "normal", condition: str | None = None,
                         confidence: float = 0.85) -> _Out:
    """Routes a parse result to the right graph shape: "ambiguous" -> ask 先后/同时 first;
    "parallel" (LLM only -- regex can't be confident) -> split/join; else a plain chain."""
    clauses = understanding["clauses"]
    actors = understanding.get("actors")
    relationship = understanding["relationship"]
    if relationship == "ambiguous":
        return _start_parallel_clarify(resume, entry_id, clauses, actors, pending, ops,
                                       edge_type=edge_type, condition=condition, confidence=confidence)
    parallel = relationship == "parallel" and len(clauses) >= 2
    if parallel:
        tail_id = _build_parallel_branches(ops, entry_id, clauses, actors, edge_type, condition, confidence)
    else:
        tail_id = _build_step_chain(ops, entry_id, clauses, actors, edge_type, condition, confidence)
    return _continue_after_step(resume, tail_id, clauses, parallel, pending, ops, graph, condition=condition)


# Rotated by how many steps are already on the graph, so the template fallback doesn't open
# every turn with the identical "记下了：" (the LLM phraser varies it further when enabled).
# A single step is already quoted by the follow-up question ("「X」之后……"), so its ack stays a
# short confirmation instead of quoting the same words twice in one bubble.
_SHORT_STEP_ACKS = ["记下了。", "嗯，", "好，这步记上了。"]
_STEP_ACK_TEMPLATES = ["记下了：{steps}。", "好，{steps}。", "{steps}，都记上了。"]


def _step_ack(clauses: list[str], parallel: bool, graph: dict, condition: str | None = None) -> str:
    quoted = [f"「{c}」" for c in clauses]
    steps = f"{'和'.join(quoted)}同时进行" if parallel else " → ".join(quoted)
    if condition:
        return f"记下了：「{condition}」时，{steps}。"
    index = len(_activities(graph))
    if len(clauses) == 1:
        return _SHORT_STEP_ACKS[index % len(_SHORT_STEP_ACKS)]
    return _STEP_ACK_TEMPLATES[index % len(_STEP_ACK_TEMPLATES)].format(steps=steps)


def _continue_after_step(resume: str, tail_id: str, clauses: list[str], parallel: bool, pending: dict,
                         ops: list[dict], graph: dict, condition: str | None = None) -> _Out:
    ack = _step_ack(clauses, parallel, graph, condition)
    if resume == "branch_b":
        return _ask_branch_rejoin(ack, tail_id, pending, ops, graph)
    # resume == "main_path": keep collecting steps until the expert says it's done.
    if parallel:
        question = "这几件事都做完之后，下一步是谁做什么？"
    else:
        question = f"「{clauses[-1]}」之后，下一步是谁做什么？"
    # The only chip is the generic "done" fallback, valid for any wording of the question --
    # so the phraser may reword this one (see guide_phrasing module docstring).
    nq = {**_q("main_path_discovery", "P0", question, chips=[END_CHIP]), "rephrasable": True}
    return _Out(ack, ops, nq, _st("main_path", tail_id, pending))


def _start_parallel_clarify(resume: str, from_id: str, clauses: list[str], actors: list | None,
                            pending: dict, ops: list[dict], edge_type: str = "normal",
                            condition: str | None = None, confidence: float = 0.85) -> _Out:
    """Defer node creation and ask 先后做/同时做 for a sentence split on an ambiguous
    connector (并/并且/同时). Clauses are stashed, never re-derived from the chip text."""
    compound = {"resume": resume, "from_id": from_id, "clauses": clauses, "actors": actors,
                "edge_type": edge_type, "condition": condition, "confidence": confidence}
    joined = "」和「".join(clauses)
    nq = _q("parallel_merge_discovery", "P2", f"「{joined}」这两件事，是先后做，还是同时做？",
            chips=PARALLEL_CLARIFY_CHIPS)
    return _Out("", ops, nq, _st("compound_parallel_clarify", None, {**pending, "_compound": compound}))


_NOT_SIMULTANEOUS_RE = re.compile(r"不(是)?同时|没有?同时|并非同时|不能同时")


def _says_simultaneous(text: str) -> bool:
    # "不是同时做" contains "同时" -- substring matching alone would read it as parallel.
    return "同时" in text and not _NOT_SIMULTANEOUS_RE.search(text)


def _resolve_parallel_clarify(text: str, pending: dict, ops: list[dict], graph: dict) -> _Out:
    compound = pending["_compound"]
    pending = {k: v for k, v in pending.items() if k != "_compound"}
    args = (compound["clauses"], compound.get("actors"), compound["edge_type"], compound["condition"],
            compound["confidence"])
    parallel = _says_simultaneous(text)
    if parallel:
        tail_id = _build_parallel_branches(ops, compound["from_id"], *args)
    else:
        # "先后做" or "不确定，再想想": default to sequential, the honest fallback.
        tail_id = _build_step_chain(ops, compound["from_id"], *args)
    return _continue_after_step(compound["resume"], tail_id, compound["clauses"], parallel, pending, ops, graph,
                                condition=compound["condition"])


def _activity_node(label: str, actor: str | None, confidence: float) -> dict:
    node = _node(_nid(), "activity", label, confidence)
    if actor:
        node["actor_roles"] = [actor]
    return node


def _build_step_chain(ops: list[dict], from_id: str, clauses: list[str], actors: list | None,
                      edge_type: str = "normal", condition: str | None = None,
                      confidence: float = 0.85) -> str:
    """One activity node per clause, chained; the first edge carries edge_type/condition."""
    prev_id = from_id
    for i, clause in enumerate(clauses):
        node = _activity_node(clause, (actors or [None] * len(clauses))[i], confidence)
        ops.append({"op": "add_node", "node": node})
        edge = _edge(prev_id, node["node_id"], edge_type if i == 0 else "normal", confidence)
        if i == 0 and condition:
            edge["condition"] = condition
        ops.append({"op": "add_edge", "edge": edge})
        prev_id = node["node_id"]
    return prev_id


def _build_parallel_branches(ops: list[dict], from_id: str, clauses: list[str], actors: list | None,
                             edge_type: str = "normal", condition: str | None = None,
                             confidence: float = 0.85) -> str:
    """parallel_split -> one activity per clause -> parallel_join; returns the join id."""
    split_id, join_id = _nid(), _nid()
    ops.append({"op": "add_node", "node": _node(split_id, "parallel_split", "并行拆分", confidence)})
    entry = _edge(from_id, split_id, edge_type, confidence)
    if condition:
        entry["condition"] = condition
    ops.append({"op": "add_edge", "edge": entry})
    tails = []
    for i, clause in enumerate(clauses):
        node = _activity_node(clause, (actors or [None] * len(clauses))[i], confidence)
        ops.append({"op": "add_node", "node": node})
        ops.append({"op": "add_edge", "edge": _edge(split_id, node["node_id"], "parallel", confidence)})
        tails.append(node["node_id"])
    ops.append({"op": "add_node", "node": _node(join_id, "parallel_join", "并行汇合", confidence)})
    for t in tails:
        ops.append({"op": "add_edge", "edge": _edge(t, join_id, "parallel", confidence)})
    return join_id


# --- Parser (step understanding) ----------------------------------------------------------

_DISCOVERY_PREFIX_RE = re.compile(
    r"^(是)?[^，,。]{0,20}(发现的|发现|反馈的|反馈|报告的|报告|上报的|上报)[，,、]\s*"
)

_STEP_FILLER_PREFIX_RE = re.compile(
    r"^(第一时间就|第一时间|立即就|立即|马上就|马上|随即就|随即|随后就|随后|接着就|接着|然后就|然后|先|再)\s*"
)

# Fixed, closed set of coordinating connectors treated as "these join two actions".
_STEP_SPLIT_RE = re.compile(r"[，,]?\s*(?:并且|并|同时|然后)\s*|、")


def _extract_step_clauses(text: str, max_steps: int = 2) -> list[str]:
    """Rule-based fallback: split expert free text into 1-2 step clauses on a fixed set of
    connectors. Not summarization -- every output word is the expert's; only a leading
    "who discovered this" clause and leading timing filler words are removed."""
    cleaned = _DISCOVERY_PREFIX_RE.sub("", text.strip())
    parts = [p.strip() for p in _STEP_SPLIT_RE.split(cleaned) if p and p.strip()]
    if not parts:
        parts = [cleaned]
    if len(parts) > max_steps:
        parts = parts[: max_steps - 1] + ["、".join(parts[max_steps - 1:])]
    result = []
    for p in parts:
        p = _STEP_FILLER_PREFIX_RE.sub("", p).strip("，,。 ").strip()
        if p:
            result.append(p[:40])
    return result or [text.strip()[:40]]


_AMBIGUOUS_CONNECTOR_RE = re.compile(r"并且|并|同时")


def _needs_parallel_clarify(text: str) -> bool:
    """True when the split produced exactly two clauses on an ambiguous connector."""
    if len(_extract_step_clauses(text)) != 2:
        return False
    cleaned = _DISCOVERY_PREFIX_RE.sub("", text.strip())
    m = _STEP_SPLIT_RE.search(cleaned)
    return bool(m and _AMBIGUOUS_CONNECTOR_RE.search(m.group(0)))


_STEP_UNDERSTANDING_SYSTEM_PROMPT = """你是一个制造业专家访谈助手的解析模块，只负责把专家刚才说的一句话解析成结构化 JSON，不做总结、改写，也不能编造专家没说过的内容——clauses 里的每个字都必须能在专家原话里找到依据。

只输出一个 JSON object，字段：
- "clauses"：字符串数组。每个元素是专家描述的一个具体动作步骤，用专家自己的措辞提炼（去掉"是谁发现的/怎么知道的"这类背景交代、去掉"第一时间就"这类时序填充词），不要整句话不加处理地原样放进去。如果整句话只描述一件事，返回只有一个元素的数组。
- "actors"：字符串数组，长度与 clauses 相同。第 i 个元素是专家原话里明确说出的、执行第 i 个步骤的人或岗位（原样摘录，例如"班组长""质检员""我"）；原话没说是谁做的，就填空字符串 ""，绝对不要猜。
- "relationship"：当 clauses 长度 >= 2 时，说明这些步骤之间的关系："serial"（先后顺序做）、"parallel"（同时做）、"ambiguous"（原话没说清楚，需要跟专家确认，不要自己猜）。clauses 长度为 1 时固定填 "serial"。

只输出 JSON，不要有任何其他文字。"""


_CORRECTION_SYSTEM_PROMPT = """你是一个制造业专家访谈助手的解析模块。除了把专家这句话解析成步骤描述之外，你还要判断一件事：专家这句话主要是在更正/撤回自己刚才说过的内容（比如"我说错了""不对，应该是""刚才说错了"这类），还是在正常回答当前问题、描述新的一步。

只输出一个 JSON object，字段：
- "is_correction"：boolean。true 表示这句话主要是在更正/撤回之前的内容。只有整体意思确实是在更正时才填 true——文字里出现"不对"这类词，但整体还是在正常描述业务事实（比如"这个判断标准不对称"），要填 false，不能只看字面关键词。
- "clauses"：字符串数组。每个元素是一个具体动作步骤，用专家自己的措辞提炼（去掉背景交代和"第一时间就"这类时序填充词）。is_correction 为 true 时，这里放专家想要更正成的新描述，取不到就放一个整体概括。
- "actors"：字符串数组，长度与 clauses 相同，原话里明确说出的执行人，没说就填 ""，不要猜。
- "relationship"："serial"/"parallel"/"ambiguous"，clauses 长度 1 时固定 "serial"；原话没说清先后还是同时，填 "ambiguous"。

只输出 JSON，不要有任何其他文字。"""


def _llm_parse(text: str, slot_config: dict, system_prompt: str, want_correction: bool) -> dict | None:
    """Returns None on ANY failure so the caller falls back to the rule-based path.

    Auto-upgrade: if the primary slot fails for any reason (timeout / network / bad
    JSON / schema mismatch) AND a higher tier (C_flagship) is configured and reachable,
    retry once with the higher tier before giving up. This keeps the local 35B (free,
    offline) as the default while letting cloud kick in when the local model can't
    keep up. We never silently degrade to a fake success; both attempts either return
    a parsed dict or raise back to the rule-based path.
    """
    def _attempt(cfg: dict) -> dict[str, Any] | None:
        try:
            parsed = llm_client.chat_completion_json(cfg, [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ])
        except llm_client.LLMError:
            return None
        clauses = parsed.get("clauses")
        if (not isinstance(clauses, list) or not clauses
                or not all(isinstance(c, str) and c.strip() for c in clauses)):
            return None
        return parsed  # schema validation done below, once

    parsed = _attempt(slot_config)
    if parsed is None:
        # Try C_flagship once. Same merge rules as the slot config (resolve_slot_for_call
        # returns the merged level config), but pinned to C_flagship regardless of the
        # primary slot's level.
        try:
            effective = app_settings.get_effective_settings()
            # Build a C_flagship config explicitly. We do NOT reuse resolve_slot_for_call()
            # because the slot-level overrides (enabled/temperature) belong to the primary
            # caller; C_flagship here is a fixed upgrade target with primary's temperature.
            level_cfg = (effective.get("llm_levels") or {}).get("C_flagship") or {}
            if level_cfg.get("endpoint") and level_cfg.get("model_name"):
                upgrade_cfg = {
                    "level": "C_flagship",
                    "enabled": True,
                    "temperature": slot_config.get("temperature", 0.2),
                    "endpoint": level_cfg.get("endpoint", ""),
                    "model_name": level_cfg.get("model_name", ""),
                    "api_key": level_cfg.get("api_key", ""),
                }
                parsed = _attempt(upgrade_cfg)
        except Exception:
            parsed = None
    if parsed is None:
        return None

    clauses = parsed.get("clauses")
    clauses = [c.strip()[:60] for c in clauses]
    relationship = parsed.get("relationship") if len(clauses) >= 2 else "serial"
    if relationship not in ("serial", "parallel", "ambiguous"):
        return None

    # Actors are optional; any actor not literally present in the expert's words is dropped
    # (PRD 3.2: 不得编造角色) rather than failing the whole parse.
    actors = parsed.get("actors")
    if isinstance(actors, list) and len(actors) == len(clauses):
        actors = [a.strip()[:20] if isinstance(a, str) and a.strip() and a.strip() in text else None
                  for a in actors]
    else:
        actors = None

    result = {"clauses": clauses, "relationship": relationship, "actors": actors}
    if want_correction:
        is_correction = parsed.get("is_correction")
        if not isinstance(is_correction, bool):
            return None
        result["is_correction"] = is_correction
    return result


def _guide_slot() -> dict | None:
    slot_config = app_settings.resolve_slot_for_call(app_settings.get_effective_settings(), "guide_service")
    if slot_config.get("enabled") and slot_config.get("endpoint") and slot_config.get("model_name"):
        return slot_config
    return None


def _rule_based_understanding(text: str) -> dict:
    return {"clauses": _extract_step_clauses(text),
            "relationship": "ambiguous" if _needs_parallel_clarify(text) else "serial",
            "actors": None}


def _understand_step(text: str) -> dict:
    """{"clauses", "relationship", "actors"} -- real LLM when configured, regex otherwise."""
    slot_config = _guide_slot()
    if slot_config:
        result = _llm_parse(text, slot_config, _STEP_UNDERSTANDING_SYSTEM_PROMPT, want_correction=False)
        if result is not None:
            return result
    return _rule_based_understanding(text)


def _understand_step_and_check_correction(text: str) -> dict:
    """Same as `_understand_step` plus `is_correction`. The rule-based fallback always says
    False (see module docstring)."""
    slot_config = _guide_slot()
    if slot_config:
        result = _llm_parse(text, slot_config, _CORRECTION_SYSTEM_PROMPT, want_correction=True)
        if result is not None:
            return result
    return {**_rule_based_understanding(text), "is_correction": False}


def _understand(text: str, skip_correction_check: bool) -> dict:
    return _understand_step(text) if skip_correction_check else _understand_step_and_check_correction(text)


def _start_correction_pick(stage: str, cursor: str | None, pending: dict, text: str) -> _Out:
    """The model flagged this turn as a correction. Ask before discarding anything -- the
    router fills in the candidate turns plus a "不是，这是新的一步" option as chips."""
    correction = {"original_stage": stage, "original_cursor": cursor,
                  "original_pending": {k: v for k, v in pending.items() if k != "_correction"},
                  "original_text": text}
    nq = _q("correction_turn_pick", "P0", "你是想改前面说过的内容吗？要改的话，选一下从哪一步开始重新讲。")
    return _Out("", [], nq, _st("awaiting_turn_selection_setup", cursor, {**pending, "_correction": correction}))


# --- Cue memory -----------------------------------------------------------------------------

_CUE_PATTERNS = {
    "branch": re.compile(r"如果|要是|假如|万一|看情况|分情况|否则|不然的话"),
    "approval": re.compile(r"审批|批准|签字|放行|请示|同意后"),
    "retry": re.compile(r"返工|重做|重新做|复检|再测一次|退回"),
}


def _record_cues(pending: dict, text: str) -> dict:
    """Remember the first clause where the expert hinted at a branch / approval / rework, so
    the matching sweep can quote it back ("你前面提到「如果尺寸超差」……") instead of asking
    in the abstract. Quotes are the expert's own clause, never paraphrased."""
    cues = dict(pending.get("cues", {}))
    for kind, pattern in _CUE_PATTERNS.items():
        if kind in cues:
            continue
        for clause in re.split(r"[，,。；;！!？?]", text):
            if pattern.search(clause) and clause.strip():
                cues[kind] = clause.strip()[:20]
                break
    return {**pending, "cues": cues} if cues else pending


# --- Small helpers --------------------------------------------------------------------------

def _q(target: str, priority: str, question: str, chips: list[str] | None = None,
       chip_mode: str | None = None) -> dict:
    nq = {"target": target, "priority": priority, "question": question, "chips": chips}
    if chip_mode:
        nq["chip_mode"] = chip_mode
    return nq


def _st(stage: str, cursor: str | None, pending: dict) -> dict:
    return {"stage": stage, "cursor": cursor, "pending": pending}


def _nid() -> str:
    return uuid.uuid4().hex[:8]


def _node(node_id: str, node_type: str, label: str, confidence: float) -> dict:
    return {"node_id": node_id, "node_type": node_type, "label": label, "source_turn_ids": [],
            "confidence": confidence, "expert_confirmed": False}


def _edge(src: str, dst: str, edge_type: str, confidence: float) -> dict:
    return {"edge_id": _nid(), "from": src, "to": dst, "edge_type": edge_type,
            "confidence": confidence, "expert_confirmed": False}


def _preview(graph: dict, ops: list[dict]) -> dict:
    """The graph as it will look once this turn's ops are applied (without mutating it)."""
    return graph_ops.apply_ops(copy.deepcopy(graph), copy.deepcopy(ops))


def _get_node(g: dict, node_id: str) -> dict | None:
    return next((n for n in g["nodes"] if n["node_id"] == node_id), None)


def _out_edges(g: dict, node_id: str) -> list[dict]:
    return [e for e in g["edges"] if e["from"] == node_id]


def _in_edges(g: dict, node_id: str) -> list[dict]:
    return [e for e in g["edges"] if e["to"] == node_id]


def _activities(g: dict) -> list[dict]:
    return [n for n in g["nodes"] if n["node_type"] == "activity"]


def _node_id_by_label(g: dict, text: str) -> str | None:
    t = text.strip().strip("「」")
    return next((n["node_id"] for n in g["nodes"] if n["label"] == t), None)


def _downstream(g: dict, start_id: str) -> list[dict]:
    """BFS order from `start_id` (inclusive)."""
    seen, order, queue = set(), [], [start_id]
    while queue:
        nid = queue.pop(0)
        if nid in seen:
            continue
        seen.add(nid)
        node = _get_node(g, nid)
        if node:
            order.append(node)
        queue += [e["to"] for e in _out_edges(g, nid)]
    return order


def _ancestors(g: dict, node_id: str) -> list[dict]:
    """Nearest-first ancestors of `node_id` (exclusive)."""
    seen, order, queue = {node_id}, [], [e["from"] for e in _in_edges(g, node_id)]
    while queue:
        nid = queue.pop(0)
        if nid in seen:
            continue
        seen.add(nid)
        node = _get_node(g, nid)
        if node:
            order.append(node)
        queue += [e["from"] for e in _in_edges(g, nid)]
    return order


def _short(label: str) -> str:
    return label if len(label) <= _CHIP_LABEL_MAX else label[: _CHIP_LABEL_MAX - 1] + "…"


def _make_options(nodes: list[dict]) -> dict[str, str]:
    """chip text -> node id. Chip text is the node's own label (the expert's words),
    shortened for display; duplicates get a numeric suffix so every chip is unambiguous."""
    options: dict[str, str] = {}
    for n in nodes:
        chip = _short(n["label"])
        i = 2
        while chip in options:
            chip = f"{_short(n['label'])}（{i}）"
            i += 1
        options[chip] = n["node_id"]
    return options


_NEGATIVE_RE = re.compile(r"^(没有|没|无|不是|不用|不需要|不会|都不|否)")


def _is_negative(text: str) -> bool:
    return bool(_NEGATIVE_RE.match(text.strip()))


def _strip_filler(text: str) -> str:
    return _STEP_FILLER_PREFIX_RE.sub("", text.strip()).strip("，,。 ")


def _first_clause(text: str, max_len: int = 20) -> str | None:
    """The expert's first clause, if it's short enough to quote back whole -- never a
    mid-sentence truncation, which reads mechanical."""
    clause = re.split(r"[，,。；;！!？?]", text.strip())[0].strip()
    return clause if 0 < len(clause) <= max_len else None


def _multiselect(text: str) -> list[str]:
    # Split only on "、" (what the frontend joins picks with) and commas -- not on "/",
    # which appears inside chip labels like "缺备件/物料".
    parts = re.split(r"[、,，]+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _split_condition(text: str) -> tuple[str, str]:
    """Best-effort "<condition>，<what happens>" split; no separator -> all condition."""
    for sep in ("，", ",", "：", ":"):
        if sep in text:
            head, _, tail = text.partition(sep)
            return head.strip(), tail.strip()
    return text.strip(), ""


def _case_context_set(pending: dict, field_name: str, value: str) -> dict:
    cc = dict(pending.get("case_context", {}))
    cc[field_name] = value
    return {**pending, "case_context": cc}


def _case_context_mark_skipped(pending: dict, field_name: str) -> dict:
    cc = dict(pending.get("case_context", {}))
    skipped = list(cc.get("skipped_fields", []))
    if field_name not in skipped:
        skipped.append(field_name)
    cc["skipped_fields"] = skipped
    cc.setdefault(field_name, "")
    return {**pending, "case_context": cc}


# --- Graph regeneration (左栏「...」菜单 -> 用大模型根据会话内容重新生成流程图) -------------
#
# Different shape from `_understand_step`: that one turns *one sentence* into clauses for the
# FSM to place node-by-node as the conversation goes; this turns the *entire transcript* into
# a complete replacement Graph in one call. There's no rule-based fallback for that -- a
# regex pass has no way to approximate "read this whole conversation and produce a DAG" the
# way it can approximate "split this one sentence on 并/同时" -- so unlike `_understand_step`,
# any failure here (slot disabled/unconfigured, network, malformed output) raises
# `llm_client.LLMError` instead of degrading to something else. The caller
# (routers/expert_workflows.py::regenerate_graph) is responsible for leaving the existing
# graph untouched when this raises, and for the "already in a published dataset -> refuse
# before ever calling this" gate -- this function only knows how to build a graph from text,
# not what's allowed to call it.

_VALID_NODE_TYPES = {
    "start", "activity", "decision", "parallel_split", "parallel_join",
    "merge", "approval", "handoff", "wait", "end",
}
_VALID_EDGE_TYPES = {
    "normal", "conditional", "parallel", "merge", "handoff", "approval",
    "timeout", "exception_forward",
}

_REGENERATE_SYSTEM_PROMPT = """你是一个制造业专家访谈助手的流程图整理模块。下面会给你一整段专家访谈的对话记录（助手的提问 + 专家的回答），请你根据专家实际说过的内容，重新整理出一张完整的流程图（DAG，有向无环图）。

严格规则：
- 只使用专家在对话里明确说过的步骤/判断/分支/并行/审批/等待/重试等信息，不要编造对话里没有出现过的节点或分支。
- 每个节点的 label 用专家自己的措辞提炼，不要整句话不加处理地照抄，也不要过度概括丢掉关键信息。
- 图必须是有向无环图：不允许出现环——返工/重试请通过 retry_semantics 表达语义，不要建一条指回之前节点的边。
- 必须有且只应有你能从对话里确认的 start 和 end 节点。

只输出一个 JSON object，字段：
- "nodes"：数组，每个元素 {"node_id": 短字符串（如 "n1"）, "node_type": 以下之一：start/activity/decision/parallel_split/parallel_join/merge/approval/handoff/wait/end, "label": 字符串, "actor_roles": 字符串数组（提到了谁负责就填谁，没提到就空数组）, "decision_question": 字符串或 null（仅 decision 节点，问题是什么）}
- "edges"：数组，每个元素 {"edge_id": 短字符串（如 "e1"）, "from": 起点 node_id, "to": 终点 node_id, "edge_type": 以下之一：normal/conditional/parallel/merge/handoff/approval/timeout/exception_forward, "condition": 字符串或 null（仅 conditional 边，条件是什么）}
- "start_node_ids"：字符串数组，start 节点的 node_id
- "end_node_ids"：字符串数组，end 节点的 node_id

只输出 JSON，不要有任何其他文字。"""


def _coerce_regenerated_graph(parsed: dict) -> dict | None:
    """Validates + normalizes the model's raw JSON into the same shape `graph_ops.new_graph()`
    produces (so it can replace `record["graph"]` directly and go through the usual
    `graph_validator.validate` afterward). Returns None on any structural problem -- the
    caller turns that into an `LLMError("bad_response", ...)`, same spirit as
    `_llm_understand_step`'s None-on-bad-shape contract.
    """
    raw_nodes = parsed.get("nodes")
    raw_edges = parsed.get("edges")
    if not isinstance(raw_nodes, list) or not raw_nodes or not isinstance(raw_edges, list):
        return None

    nodes: list[dict] = []
    node_ids: set[str] = set()
    for n in raw_nodes:
        if not isinstance(n, dict):
            return None
        node_id, node_type, label = n.get("node_id"), n.get("node_type"), n.get("label")
        if not isinstance(node_id, str) or not node_id or node_id in node_ids:
            return None
        if node_type not in _VALID_NODE_TYPES:
            return None
        if not isinstance(label, str) or not label.strip():
            return None
        node_ids.add(node_id)
        actor_roles = n.get("actor_roles")
        nodes.append({
            "node_id": node_id, "node_type": node_type, "label": label.strip()[:120],
            "actor_roles": [r for r in actor_roles if isinstance(r, str) and r.strip()] if isinstance(actor_roles, list) else [],
            "decision_question": n["decision_question"] if isinstance(n.get("decision_question"), str) else None,
            "confidence": 0.6, "expert_confirmed": False, "source_turn_ids": [],
        })

    edges: list[dict] = []
    edge_ids: set[str] = set()
    for e in raw_edges:
        if not isinstance(e, dict):
            return None
        edge_id, from_id, to_id, edge_type = e.get("edge_id"), e.get("from"), e.get("to"), e.get("edge_type")
        if not isinstance(edge_id, str) or not edge_id or edge_id in edge_ids:
            return None
        if from_id not in node_ids or to_id not in node_ids:
            return None
        if edge_type not in _VALID_EDGE_TYPES:
            return None
        edge_ids.add(edge_id)
        edges.append({
            "edge_id": edge_id, "from": from_id, "to": to_id, "edge_type": edge_type,
            "condition": e["condition"] if isinstance(e.get("condition"), str) else None,
            "confidence": 0.6, "expert_confirmed": False, "source_turn_ids": [],
        })

    start_ids = parsed.get("start_node_ids")
    end_ids = parsed.get("end_node_ids")
    if not isinstance(start_ids, list) or not all(isinstance(s, str) and s in node_ids for s in start_ids):
        start_ids = [n["node_id"] for n in nodes if n["node_type"] == "start"]
    if not isinstance(end_ids, list) or not all(isinstance(s, str) and s in node_ids for s in end_ids):
        end_ids = [n["node_id"] for n in nodes if n["node_type"] == "end"]

    return {"graph_type": "dag", "start_node_ids": start_ids, "end_node_ids": end_ids, "nodes": nodes, "edges": edges}


def regenerate_graph_from_transcript(turns: list[dict[str, str]]) -> dict:
    """Full transcript -> full replacement Graph, via the `graph_regenerate` LLM slot. Raises
    `llm_client.LLMError` on any failure (not configured/disabled, network/timeout, malformed
    or structurally invalid output) -- see the module comment above for why there's no
    fallback path here, unlike `_understand_step`.
    """
    slot_config = app_settings.resolve_slot_for_call(app_settings.get_effective_settings(), "graph_regenerate")
    if not (slot_config.get("enabled") and slot_config.get("endpoint") and slot_config.get("model_name")):
        raise llm_client.LLMError("not_configured", "「重新生成流程图」环节未配置可达的推理服务（请到系统设置里配置）")

    transcript = "\n".join(
        f"{'专家' if t['role'] == 'expert' else '助手'}：{t['text']}" for t in turns
    )
    parsed = llm_client.chat_completion_json(slot_config, [
        {"role": "system", "content": _REGENERATE_SYSTEM_PROMPT},
        {"role": "user", "content": transcript},
    ])
    graph = _coerce_regenerated_graph(parsed)
    if graph is None:
        raise llm_client.LLMError("bad_response", f"模型输出的流程图结构不符合预期格式：{parsed!r}"[:500])
    return graph
