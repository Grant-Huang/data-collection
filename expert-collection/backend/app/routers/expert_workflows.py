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
        "opening", "trigger_detail", "main_path", "branch_check", "branch_condition_a",
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

    assistant_reply, ops, next_question, new_state = guide_service.handle_turn(state, req.text)
    record["graph"] = graph_ops.apply_ops(record["graph"], ops)
    record["_guide_state"] = new_state
    record["stage"] = new_state["stage"]

    assistant_turn_id = uuid.uuid4().hex[:8]
    record["turns"].append({"turn_id": assistant_turn_id, "role": "assistant", "text": assistant_reply})

    issues = graph_validator.validate(record["graph"])
    score = _completion_score(record)
    ready = new_state["stage"] == "review" and graph_validator.is_valid(record["graph"])
    record["completion"] = {"score": score, "ready_for_confirmation": ready}
    record["unresolved"] = [next_question] if next_question else []
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
    record["updated_at"] = _now()
    db.save(record)
    return WorkflowRecord.model_validate(_strip_internal(record))
