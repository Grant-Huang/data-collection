"""API endpoints from PRD section 6.4, wiring guide_service + graph_ops + graph_validator + db
into the desktop expert-conversation loop (Phase 1 scope: no dataset/dashboard/experiment
endpoints here -- those are Phase 3/4).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from .. import db, graph_ops, graph_validator, guide_service
from ..models import (
    Completion,
    CreateWorkflowRequest,
    TurnRequest,
    TurnResponse,
    ValidationIssue,
    WorkflowRecord,
    WorkflowSummary,
)

router = APIRouter(prefix="/api/expert-workflows", tags=["expert-workflows"])

# IMPLEMENTATION_PLAN.md section 14, §15.1-①(c) -- correction/rollback. guide_service.py owns
# detecting "is this a correction" and asking which turn to roll back to (in one combined
# step -- "not a correction" is just one more chip option alongside the candidate turns, not
# a separate yes/no question first), but the actual candidate list and the rollback itself
# need the full graph + turn transcript, which only this router has.
_MAX_CORRECTION_CANDIDATES = 5
# The chip label for "this wasn't a correction, resume normal processing" -- appended to the
# candidate list built below, never itself a real turn_id.
_CORRECTION_DECLINE_LABEL = "不是，这是新的一步"
# Stages a turn answers where its own "content" is a piece of internal correction-flow
# machinery, not something the expert would recognize as a rollback target -- excluded from
# the candidate list, but NOT excluded from the rollback cutoff itself (see _rollback_to_turn:
# the cutoff is always "everything from the picked turn's position in the log onward",
# regardless of stage, so a deferred compound_parallel_clarify answer's graph content is still
# correctly swept up even though the turn that triggered the ambiguity is what gets offered
# as the candidate).
_CORRECTION_META_STAGES = {"compound_parallel_clarify", "awaiting_turn_selection_setup", "awaiting_turn_selection"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _completion_score(record: dict) -> float:
    """Simple, explainable completion heuristic for Phase 1: how far the Mock Guide Service's
    fixed interview stages have progressed, since the real scoring model (PRD 8/13) is
    out of scope until Phase 3. Kept as a plain ratio so it's easy to explain to the expert,
    per the product principle that results always need a plain-language explanation.
    """
    stage = record["stage"]
    order = [
        "opening", "scenario_trigger", "scenario_goal", "scenario_success",
        "context_known", "context_known_clarify", "context_unknown", "context_unknown_clarify",
        "context_constraints", "context_constraints_clarify", "context_resources", "context_resources_clarify",
        "trigger_detail", "main_path", "branch_check", "branch_condition_a",
        "branch_condition_b", "merge_check", "parallel_check", "parallel_branch_a",
        "parallel_branch_b", "approval_check", "approval_who", "retry_check",
        "retry_target", "end_condition", "review",
    ]
    try:
        idx = order.index(stage)
    except ValueError:
        idx = 0
    return round(idx / (len(order) - 1), 2)


@router.post("", response_model=WorkflowRecord)
def create_workflow(req: CreateWorkflowRequest) -> WorkflowRecord:
    workflow_id = uuid.uuid4().hex[:12]
    now = _now()
    graph = graph_ops.new_graph()
    reply, next_question = guide_service.initial_turn()
    state = guide_service.initial_state()
    record = {
        "id": workflow_id,
        "name": req.name or f"专家会话 {workflow_id}",
        "status": "collecting",
        "stage": state["stage"],
        "graph": graph,
        "turns": [{"turn_id": uuid.uuid4().hex[:8], "role": "assistant", "text": reply}],
        "unresolved": [next_question] if next_question else [],
        "completion": {"score": 0.0, "ready_for_confirmation": False},
        "validation": graph_validator.validate(graph),
        "case_context": None,
        "created_at": now,
        "updated_at": now,
        "_guide_state": state,
    }
    db.save(record)
    return WorkflowRecord.model_validate(_strip_internal(record))


def _strip_internal(record: dict) -> dict:
    return {k: v for k, v in record.items() if not k.startswith("_")}


@router.get("", response_model=list[WorkflowSummary])
def list_workflows() -> list[WorkflowSummary]:
    records = db.list_all()
    return [
        WorkflowSummary(
            id=r["id"], name=r["name"], status=r["status"],
            completion_score=r["completion"]["score"], updated_at=r["updated_at"],
        )
        for r in records
    ]


@router.get("/{workflow_id}", response_model=WorkflowRecord)
def get_workflow(workflow_id: str) -> WorkflowRecord:
    record = db.get(workflow_id)
    if not record:
        raise HTTPException(status_code=404, detail="workflow not found")
    return WorkflowRecord.model_validate(_strip_internal(record))


def _describe_turn(record: dict, turn_id: str) -> str:
    """Human-readable description of what one expert turn produced, for the correction
    "which turn do you want to roll back to" picker. Built entirely from the graph's own data
    (structural nodes like parallel_split/parallel_join are excluded from the label text, but
    a parallel_split among this turn's nodes is what decides the "（同时做）" suffix) and,
    when the turn produced no graph nodes at all (e.g. a Scenario/Case Context answer), the
    expert's own words -- never a fabricated summary.
    """
    nodes = [n for n in record["graph"]["nodes"] if turn_id in n.get("source_turn_ids", [])]
    content_nodes = [n for n in nodes if n["node_type"] in ("activity", "start", "end")]
    if content_nodes:
        labels = [n["label"] for n in content_nodes]
        is_parallel = any(n["node_type"] == "parallel_split" for n in nodes)
        joined = "」+「".join(labels)
        suffix = "（同时做）" if is_parallel and len(labels) > 1 else ""
        return f"「{joined}」{suffix}"
    turn = next((t for t in record["turns"] if t["turn_id"] == turn_id), None)
    text = turn["text"] if turn else ""
    return f"「{text[:24]}」" if text else "（这一轮，无更多信息）"


def _correction_candidates(record: dict, limit: int = _MAX_CORRECTION_CANDIDATES) -> list[tuple[str, str]]:
    """Most-recent-first (turn_id, description) pairs to offer as rollback targets. Each entry
    is one full expert turn -- the granularity the design settled on is "a turn", never a
    single node inside a multi-node/parallel turn, since a parallel structure is always built
    atomically within one turn and so never has an individually-selectable midpoint.
    """
    log = record.get("_turn_state_log", [])
    real = [entry for entry in log if entry["state_before"]["stage"] not in _CORRECTION_META_STAGES]
    recent = real[-limit:]
    return [(entry["turn_id"], _describe_turn(record, entry["turn_id"])) for entry in reversed(recent)]


def _rollback_to_turn(record: dict, turn_id: str) -> str:
    """Removes every node/edge tagged with `turn_id` or any turn after it, restores the FSM
    state to what it was right before that turn was originally processed, truncates the
    transcript and turn log to match, and returns the assistant question that led to that
    turn in the first place (so the caller can re-ask it). Mutates `record` in place.
    """
    log = record["_turn_state_log"]
    idx = next(i for i, entry in enumerate(log) if entry["turn_id"] == turn_id)
    cutoff_ids = {entry["turn_id"] for entry in log[idx:]}

    remove_ops = [
        {"op": "remove_node", "node_id": n["node_id"]}
        for n in record["graph"]["nodes"] if cutoff_ids & set(n.get("source_turn_ids", []))
    ] + [
        {"op": "remove_edge", "edge_id": e["edge_id"]}
        for e in record["graph"]["edges"] if cutoff_ids & set(e.get("source_turn_ids", []))
    ]
    record["graph"] = graph_ops.apply_ops(record["graph"], remove_ops)

    turn_positions = {t["turn_id"]: i for i, t in enumerate(record["turns"])}
    pos = turn_positions[turn_id]
    original_question = record["turns"][pos - 1]["text"] if pos > 0 else "好，我们重新梳理这一步。"

    # Everything from the rolled-back turn onward is truncated -- including the correction/
    # confirm/pick meta-turns that led here, since their content genuinely doesn't belong to
    # the graph anymore. What happens next (the re-ask below) starts a fresh run of turns.
    record["turns"] = record["turns"][:pos]
    record["_turn_state_log"] = log[:idx]

    state_before = log[idx]["state_before"]
    record["_guide_state"] = state_before
    record["stage"] = state_before["stage"]
    record["case_context"] = state_before.get("pending", {}).get("case_context")
    return original_question


@router.post("/{workflow_id}/turns", response_model=TurnResponse)
def post_turn(workflow_id: str, req: TurnRequest) -> TurnResponse:
    record = db.get(workflow_id)
    if not record:
        raise HTTPException(status_code=404, detail="workflow not found")
    if record["status"] == "expert_confirmed":
        raise HTTPException(status_code=409, detail="workflow already confirmed, no further turns accepted")

    state = record.get("_guide_state") or {"stage": record["stage"], "cursor": None, "pending": {}}
    expert_turn_id = uuid.uuid4().hex[:8]
    record["turns"].append({"turn_id": expert_turn_id, "role": "expert", "text": req.text})

    if state["stage"] == "awaiting_turn_selection":
        # Router-handled entirely -- this is the one turn guide_service.handle_turn never
        # sees on the "roll back to an earlier turn" path, since resolving it needs the full
        # graph + turn history (see the module-level comment above _MAX_CORRECTION_CANDIDATES).
        # Picking "not a correction" does go through guide_service, though -- it's just
        # re-processing the original text at the original stage.
        options = state.get("pending", {}).get("_correction_options", {})
        picked = req.text.strip()
        if picked not in options:
            assistant_reply = "麻烦从上面列出的选项里选一个，我才知道要回退到哪一步。"
            next_question = {"target": "correction_turn_pick", "priority": "P0", "question": assistant_reply,
                              "chips": list(options.keys())}
            new_state, ops = state, []
            record["_guide_state"] = new_state
            record["stage"] = new_state["stage"]
            record["case_context"] = new_state.get("pending", {}).get("case_context")
        elif options[picked] is None:
            # "不是，这是新的一步" -- resume normal processing of the original text at the
            # original stage, as if the correction check had never fired.
            correction = state["pending"]["_correction"]
            restored_state = {"stage": correction["original_stage"], "cursor": correction["original_cursor"],
                               "pending": correction["original_pending"]}
            record.setdefault("_turn_state_log", []).append({"turn_id": expert_turn_id, "state_before": restored_state})
            assistant_reply, ops, next_question, new_state = guide_service.handle_turn(
                restored_state, correction["original_text"], turn_id=expert_turn_id, skip_correction_check=True,
            )
            record["graph"] = graph_ops.apply_ops(record["graph"], ops)
            record["_guide_state"] = new_state
            record["stage"] = new_state["stage"]
            record["case_context"] = new_state.get("pending", {}).get("case_context")
        else:
            original_question = _rollback_to_turn(record, options[picked])
            assistant_reply = f"好，已经回退。{original_question}"
            new_state = record["_guide_state"]
            next_question = {"target": new_state["stage"], "priority": "P0", "question": original_question,
                              "chips": None}
            ops = []
            record["_guide_state"] = new_state
            record["stage"] = new_state["stage"]
            record["case_context"] = new_state.get("pending", {}).get("case_context")
    else:
        record.setdefault("_turn_state_log", []).append({"turn_id": expert_turn_id, "state_before": state})
        assistant_reply, ops, next_question, new_state = guide_service.handle_turn(state, req.text, turn_id=expert_turn_id)
        record["graph"] = graph_ops.apply_ops(record["graph"], ops)
        record["_guide_state"] = new_state
        record["stage"] = new_state["stage"]
        record["case_context"] = new_state.get("pending", {}).get("case_context")

        if new_state["stage"] == "awaiting_turn_selection_setup":
            # guide_service asked to defer to a turn picker but can't build the candidate list
            # itself (no graph/turn-history access) -- fill it in here before this response
            # goes to the frontend. The "not a correction" option rides in the same chip list
            # (see the module-level comment on _CORRECTION_DECLINE_LABEL) rather than a
            # separate yes/no question first.
            candidates = _correction_candidates(record)
            options = {desc: tid for tid, desc in candidates}
            options[_CORRECTION_DECLINE_LABEL] = None
            next_question["chips"] = list(options.keys())
            new_state = {**new_state, "stage": "awaiting_turn_selection",
                         "pending": {**new_state["pending"], "_correction_options": options}}
            record["_guide_state"] = new_state
            record["stage"] = new_state["stage"]

    assistant_turn_id = uuid.uuid4().hex[:8]
    record["turns"].append({"turn_id": assistant_turn_id, "role": "assistant", "text": assistant_reply})

    issues = graph_validator.validate(record["graph"])
    score = _completion_score(record)
    ready = new_state["stage"] == "review" and graph_validator.is_valid(record["graph"])
    record["completion"] = {"score": score, "ready_for_confirmation": ready}
    record["unresolved"] = [next_question] if next_question else []
    record["validation"] = issues
    if ready and record["status"] != "expert_confirmed":
        record["status"] = "needs_confirmation"
    record["updated_at"] = _now()

    db.save(record)

    return TurnResponse(
        assistant_reply=assistant_reply,
        graph_ops_applied=len(ops),
        current_dag=record["graph"],
        completion=Completion(**record["completion"]),
        validation=[ValidationIssue(**i) for i in issues],
        next_question=next_question,
    )


@router.post("/{workflow_id}/confirm", response_model=WorkflowRecord)
def confirm_workflow(workflow_id: str) -> WorkflowRecord:
    record = db.get(workflow_id)
    if not record:
        raise HTTPException(status_code=404, detail="workflow not found")
    issues = graph_validator.validate(record["graph"])
    if any(i["level"] == "error" for i in issues):
        raise HTTPException(
            status_code=422,
            detail={"message": "图结构未通过校验，无法确认", "issues": issues},
        )
    record["status"] = "expert_confirmed"
    for node in record["graph"]["nodes"]:
        node["expert_confirmed"] = True
    for edge in record["graph"]["edges"]:
        edge["expert_confirmed"] = True
    record["validation"] = issues
    record["updated_at"] = _now()
    db.save(record)
    return WorkflowRecord.model_validate(_strip_internal(record))
