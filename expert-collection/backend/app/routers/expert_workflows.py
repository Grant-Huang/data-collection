"""API endpoints from PRD section 6.4, wiring guide_service + graph_ops + graph_validator + db
into the desktop expert-conversation loop (Phase 1 scope: no dataset/dashboard/experiment
endpoints here -- those are Phase 3/4).
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from .. import dataset_records, db, graph_ops, graph_validator, guide_service, llm_client, review_agent
from ..models import (
    Completion,
    CreateWorkflowRequest,
    ManufacturingContextUpdateRequest,
    RegenerateGraphCheck,
    TurnRequest,
    TurnResponse,
    WorkflowMetaUpdateRequest,
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
    """Plain, explainable progress estimate -- see guide_service.progress."""
    return guide_service.progress(record.get("_guide_state") or {"stage": record["stage"]}, record["graph"])


def _assistant_turn(text: str, next_question: dict | None) -> dict:
    """An assistant transcript entry. `text` stays the full plain message (what every
    existing consumer reads); the layered fields let the chat bubble render the
    restatement / question / why / chips separately."""
    turn = {"turn_id": uuid.uuid4().hex[:8], "role": "assistant", "text": text}
    if next_question:
        turn.update({
            "ack": next_question.get("ack"),
            "question": next_question.get("question"),
            "why": next_question.get("why"),
            "chips": next_question.get("chips"),
            "chip_mode": next_question.get("chip_mode"),
        })
    return turn


def _review_turn(result: review_agent.TurnResult, *, sample: str | None = None) -> dict:
    """Assistant transcript entry for a review-loop reply (section 17): understanding (ack),
    the concrete graph changes, a body (read-back / notices) and one question -- no chips."""
    turn = {"turn_id": uuid.uuid4().hex[:8], "role": "assistant", "text": result.text,
            "ack": result.ack, "question": result.question, "changes": result.changes or None, "body": result.body}
    if sample:
        turn["sample"] = sample
    return turn


def _apply_review_state(record: dict, state: dict) -> None:
    record["_review"] = state
    record["stage"] = f"review_{state['phase']}"
    ready = state["phase"] == "final_confirm" and graph_validator.is_valid(record["graph"])
    record["completion"] = {"score": review_agent.progress(state), "ready_for_confirmation": ready}
    record["unresolved"] = []
    record["validation"] = graph_validator.validate(record["graph"])
    if record["status"] != "expert_confirmed":
        record["status"] = "needs_confirmation" if ready else "collecting"


def _mark_confirmed(record: dict) -> None:
    record["status"] = "expert_confirmed"
    for node in record["graph"]["nodes"]:
        node["expert_confirmed"] = True
    for edge in record["graph"]["edges"]:
        edge["expert_confirmed"] = True
    if record.get("_review"):
        record["_review"]["phase"] = "done"
        record["stage"] = "review_done"
        record["completion"] = {"score": 1.0, "ready_for_confirmation": False}


@router.post("", response_model=WorkflowRecord)
def create_workflow(req: CreateWorkflowRequest) -> WorkflowRecord:
    workflow_id = uuid.uuid4().hex[:12]
    now = _now()
    graph = graph_ops.new_graph()
    if review_agent.available():
        # Section 17: narrate first, then review. Falls back to section 15's step-by-step
        # guide below when the C_standard slots aren't configured.
        state = review_agent.new_state("create")
        opening = review_agent.opening(state, graph)
        record = {
            "id": workflow_id, "name": req.name or f"专家会话 {workflow_id}", "status": "collecting",
            "stage": "", "graph": graph,
            "turns": [_review_turn(opening, sample=review_agent.SAMPLE_NARRATION)],
            "unresolved": [], "completion": {}, "validation": [], "case_context": None,
            "created_at": now, "updated_at": now, "pinned": False, "archived": False,
        }
        _apply_review_state(record, opening.state)
        db.save(record)
        return WorkflowRecord.model_validate(_strip_internal(record, in_dataset=False))

    reply, next_question = guide_service.initial_turn()
    state = guide_service.initial_state()
    record = {
        "id": workflow_id,
        "name": req.name or f"专家会话 {workflow_id}",
        "status": "collecting",
        "stage": state["stage"],
        "graph": graph,
        "turns": [_assistant_turn(reply, next_question)],
        "unresolved": [next_question] if next_question else [],
        "completion": {"score": 0.0, "ready_for_confirmation": False},
        "validation": graph_validator.validate(graph),
        "case_context": None,
        "created_at": now,
        "updated_at": now,
        "pinned": False,
        "archived": False,
        "_guide_state": state,
    }
    db.save(record)
    return WorkflowRecord.model_validate(_strip_internal(record, in_dataset=False))


def _strip_internal(record: dict, *, in_dataset: bool) -> dict:
    out = {k: v for k, v in record.items() if not k.startswith("_")}
    out["in_dataset"] = in_dataset
    return out


@router.get("", response_model=list[WorkflowSummary])
def list_workflows(include_archived: bool = False) -> list[WorkflowSummary]:
    """左栏会话清单。默认隐藏已归档会话（`include_archived=true` 时显示，配合前端「显示/
    隐藏已归档」的切换）；置顶的会话排在最前面，组内仍按 `updated_at` 倒序（db.list_all
    已经这样排好，Python 的 sort 是稳定排序，不会打乱这个次序）。
    """
    records = db.list_all()
    published = dataset_records.published_workflow_ids()
    visible = [r for r in records if include_archived or not r.get("archived", False)]
    visible.sort(key=lambda r: not r.get("pinned", False))
    return [
        WorkflowSummary(
            id=r["id"], name=r["name"], status=r["status"],
            completion_score=r["completion"]["score"], updated_at=r["updated_at"],
            pinned=r.get("pinned", False), archived=r.get("archived", False),
            in_dataset=r["id"] in published,
        )
        for r in visible
    ]


@router.get("/{workflow_id}", response_model=WorkflowRecord)
def get_workflow(workflow_id: str) -> WorkflowRecord:
    record = db.get(workflow_id)
    if not record:
        raise HTTPException(status_code=404, detail="workflow not found")
    in_dataset = bool(dataset_records.versions_containing(workflow_id))
    return WorkflowRecord.model_validate(_strip_internal(record, in_dataset=in_dataset))


@router.patch("/{workflow_id}", response_model=WorkflowRecord)
def update_workflow_meta(workflow_id: str, req: WorkflowMetaUpdateRequest) -> WorkflowRecord:
    """左栏「...」下拉菜单：重命名 / 置顶 / 归档。用归档而不是删除 -- 归档只是把会话从默认
    清单里隐藏、并从数据集草稿池里排除（见 datasets.py::_draft_pool），记录本身还在，因为已
    发布的 expert_collected 数据集版本只存 workflow_ids、导出时才回读 graph（见
    dataset_records.records_for_export），真删掉会让已发布的版本悄悄丢记录。
    """
    record = db.get(workflow_id)
    if not record:
        raise HTTPException(status_code=404, detail="workflow not found")
    patch = req.model_dump(exclude_unset=True)
    if "name" in patch:
        name = (patch["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="会话名称不能为空")
        record["name"] = name
    if "pinned" in patch:
        record["pinned"] = bool(patch["pinned"])
    if "archived" in patch:
        record["archived"] = bool(patch["archived"])
    record["updated_at"] = _now()
    db.save(record)
    in_dataset = bool(dataset_records.versions_containing(workflow_id))
    return WorkflowRecord.model_validate(_strip_internal(record, in_dataset=in_dataset))


@router.put("/{workflow_id}/manufacturing-context", response_model=WorkflowRecord)
def update_manufacturing_context(workflow_id: str, req: ManufacturingContextUpdateRequest) -> WorkflowRecord:
    """§14.4 Dataset Slice -- a static classification tag, not scenario narrative gathered
    turn by turn, so it's a plain PUT rather than another guide_service/FSM stage; editable at
    any time (before or after confirm), since re-tagging a workflow's industry/mode doesn't
    touch its graph or turns.
    """
    record = db.get(workflow_id)
    if not record:
        raise HTTPException(status_code=404, detail="workflow not found")
    record["manufacturing_context"] = req.model_dump()
    record["updated_at"] = _now()
    db.save(record)
    in_dataset = bool(dataset_records.versions_containing(workflow_id))
    return WorkflowRecord.model_validate(_strip_internal(record, in_dataset=in_dataset))


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


def _rollback_to_turn(record: dict, turn_id: str) -> dict:
    """Removes every node/edge tagged with `turn_id` or any turn after it, restores the FSM
    state to what it was right before that turn was originally processed, truncates the
    transcript and turn log to match, and returns the assistant turn that led to that turn
    in the first place (so the caller can re-ask it, chips included). Mutates `record` in
    place.

    Newer log entries carry a full `graph_before` snapshot, which is restored as-is: the
    guide's structural sweeps rewire *existing* edges (update_edge), and removing only the
    nodes/edges tagged with later turns can't undo those rewires. Older entries without a
    snapshot fall back to the tag-based removal.
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
    if "graph_before" in log[idx]:
        record["graph"] = copy.deepcopy(log[idx]["graph_before"])
    else:
        record["graph"] = graph_ops.apply_ops(record["graph"], remove_ops)

    turn_positions = {t["turn_id"]: i for i, t in enumerate(record["turns"])}
    pos = turn_positions[turn_id]
    original_turn = (record["turns"][pos - 1] if pos > 0
                     else {"text": "好，我们重新梳理这一步。", "question": "好，我们重新梳理这一步。"})

    # Everything from the rolled-back turn onward is truncated -- including the correction/
    # confirm/pick meta-turns that led here, since their content genuinely doesn't belong to
    # the graph anymore. What happens next (the re-ask below) starts a fresh run of turns.
    record["turns"] = record["turns"][:pos]
    record["_turn_state_log"] = log[:idx]

    state_before = log[idx]["state_before"]
    record["_guide_state"] = state_before
    record["stage"] = state_before["stage"]
    record["case_context"] = state_before.get("pending", {}).get("case_context")
    return original_turn


@router.post("/{workflow_id}/turns", response_model=TurnResponse)
def post_turn(workflow_id: str, req: TurnRequest) -> TurnResponse:
    record = db.get(workflow_id)
    if not record:
        raise HTTPException(status_code=404, detail="workflow not found")
    if record["status"] == "expert_confirmed":
        raise HTTPException(status_code=409, detail="workflow already confirmed, no further turns accepted")

    if record.get("_review"):
        return _post_review_turn(record, req)

    state = record.get("_guide_state") or {"stage": record["stage"], "cursor": None, "pending": {}}
    expert_turn_id = uuid.uuid4().hex[:8]
    history = list(record["turns"])
    graph_before = copy.deepcopy(record["graph"])
    expert_turn = {"turn_id": expert_turn_id, "role": "expert", "text": req.text}
    if req.raw_transcript:
        expert_turn["raw_transcript"] = req.raw_transcript
    record["turns"].append(expert_turn)

    if state["stage"] == "awaiting_turn_selection":
        # Router-handled entirely -- this is the one turn guide_service.handle_turn never
        # sees on the "roll back to an earlier turn" path, since resolving it needs the full
        # graph + turn history (see the module-level comment above _MAX_CORRECTION_CANDIDATES).
        # Picking "not a correction" does go through guide_service, though -- it's just
        # re-processing the original text at the original stage.
        options = state.get("pending", {}).get("_correction_options", {})
        picked = req.text.strip()
        if picked not in options:
            assistant_reply = "麻烦从下面的选项里选一个，我才知道要回退到哪一步。"
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
            record.setdefault("_turn_state_log", []).append(
                {"turn_id": expert_turn_id, "state_before": restored_state, "graph_before": graph_before})
            assistant_reply, ops, next_question, new_state = guide_service.handle_turn(
                restored_state, correction["original_text"], turn_id=expert_turn_id, skip_correction_check=True,
                graph=record["graph"], history=history,
            )
            record["graph"] = graph_ops.apply_ops(record["graph"], ops)
            record["_guide_state"] = new_state
            record["stage"] = new_state["stage"]
            record["case_context"] = new_state.get("pending", {}).get("case_context")
        else:
            original_turn = _rollback_to_turn(record, options[picked])
            original_question = original_turn.get("question") or original_turn["text"]
            assistant_reply = f"好，已经回退到那一步。{original_question}"
            new_state = record["_guide_state"]
            next_question = {"target": new_state["stage"], "priority": "P0", "question": original_question,
                              "chips": original_turn.get("chips"), "chip_mode": original_turn.get("chip_mode"),
                              "ack": "好，已经回退到那一步。", "why": original_turn.get("why")}
            ops = []
            record["_guide_state"] = new_state
            record["stage"] = new_state["stage"]
            record["case_context"] = new_state.get("pending", {}).get("case_context")
    else:
        record.setdefault("_turn_state_log", []).append(
            {"turn_id": expert_turn_id, "state_before": state, "graph_before": graph_before})
        assistant_reply, ops, next_question, new_state = guide_service.handle_turn(
            state, req.text, turn_id=expert_turn_id, graph=record["graph"], history=history,
        )
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

    record["turns"].append(_assistant_turn(assistant_reply, next_question))

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


def _post_review_turn(record: dict, req: TurnRequest) -> TurnResponse:
    expert_turn_id = uuid.uuid4().hex[:8]
    expert_turn = {"turn_id": expert_turn_id, "role": "expert", "text": req.text}
    if req.raw_transcript:
        expert_turn["raw_transcript"] = req.raw_transcript
    record["turns"].append(expert_turn)

    result = review_agent.handle_turn(record["_review"], record["graph"], record["turns"], req.text, expert_turn_id)
    before = len(record["graph"]["nodes"]) + len(record["graph"]["edges"])
    if result.graph is not None:
        record["graph"] = result.graph
    if result.case_context:
        record["case_context"] = {**(record.get("case_context") or {}), **result.case_context}
    record["turns"].append(_review_turn(result))
    _apply_review_state(record, result.state)
    if result.finished:
        _mark_confirmed(record)
    record["updated_at"] = _now()
    db.save(record)
    return TurnResponse(
        assistant_reply=result.text,
        graph_ops_applied=abs(len(record["graph"]["nodes"]) + len(record["graph"]["edges"]) - before),
        current_dag=record["graph"],
        completion=Completion(**record["completion"]),
        validation=[ValidationIssue(**i) for i in record["validation"]],
        next_question=None,
    )


@router.post("/{workflow_id}/reopen", response_model=WorkflowRecord)
def reopen_workflow(workflow_id: str) -> WorkflowRecord:
    """「继续修改」(section 17.1 "编辑"): a confirmed workflow that is not in any dataset goes
    back into the review loop. Refused once published -- expert_collected versions read the
    live graph, so editing would silently change published data (same rule as regenerate)."""
    record = db.get(workflow_id)
    if not record:
        raise HTTPException(status_code=404, detail="workflow not found")
    if dataset_records.versions_containing(workflow_id):
        raise HTTPException(status_code=409, detail="这个流程已经录入数据集，不能再修改")
    if record["status"] != "expert_confirmed":
        raise HTTPException(status_code=409, detail="这个流程还没有确认提交，直接在对话里修改即可")
    if not review_agent.available():
        raise HTTPException(status_code=409, detail="继续修改需要配置 AI 模型（系统管理 → 模型配置）")
    state = review_agent.new_state("edit")
    opening = review_agent.opening(state, record["graph"])
    record["status"] = "collecting"
    record["turns"].append(_review_turn(opening))
    _apply_review_state(record, opening.state)
    record["updated_at"] = _now()
    db.save(record)
    return WorkflowRecord.model_validate(_strip_internal(record, in_dataset=False))


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
    _mark_confirmed(record)
    record["validation"] = issues
    record["updated_at"] = _now()
    db.save(record)
    in_dataset = bool(dataset_records.versions_containing(workflow_id))
    return WorkflowRecord.model_validate(_strip_internal(record, in_dataset=in_dataset))


def _regenerate_check(record: dict) -> RegenerateGraphCheck:
    """Shared gate for both the pre-flight GET (frontend shows the reason instead of a
    confirm dialog) and the actual POST (never trust the client-only check -- re-verify
    server-side right before calling the LLM, in case the workflow got published in the
    meantime).

    用户的两条规则，原样实现：
    1. 流程图已经进入数据集（任何 dataset_version 引用过这个会话，包括已归档的版本）——不
       允许重新生成，因为 expert_collected 版本发布时不做快照，是发布后每次都回读当前的
       graph（见 dataset_records.records_for_export），重新生成会悄悄改掉已发布版本的内容。
    2. 还没有进入数据集——允许重新生成，但如果这个会话还在采集中（没有一条专家消息），没有
       内容可整理，也拦住。
    """
    versions = dataset_records.versions_containing(record["id"])
    if versions:
        names = "、".join(f"{v['source_type']} v{v['version_number']}" for v in versions)
        return RegenerateGraphCheck(
            allowed=False, blocked_code="in_dataset",
            reason=f"这个会话的流程图已经录入数据集（{names}），为避免悄悄改动已发布的数据，不能再重新生成。",
            dataset_versions=versions,
        )
    if not any(t["role"] == "expert" for t in record["turns"]):
        return RegenerateGraphCheck(
            allowed=False, blocked_code="no_expert_turns",
            reason="还没有专家发言内容，无法根据会话重新生成流程图。",
        )
    return RegenerateGraphCheck(
        allowed=True, will_reset_confirmation=record["status"] == "expert_confirmed",
    )


@router.get("/{workflow_id}/regenerate-check", response_model=RegenerateGraphCheck)
def regenerate_check(workflow_id: str) -> RegenerateGraphCheck:
    record = db.get(workflow_id)
    if not record:
        raise HTTPException(status_code=404, detail="workflow not found")
    return _regenerate_check(record)


@router.post("/{workflow_id}/regenerate-graph", response_model=WorkflowRecord)
def regenerate_graph(workflow_id: str) -> WorkflowRecord:
    """用大模型把整段会话重新整理成一张流程图，整体替换当前 graph，并同时重置对话进度
    （见 guide_service.state_after_regeneration：从新图的结构补问继续，已问过的不重复）。前置校验见
    `_regenerate_check`；LLM 调用失败时（未配置/超时/输出格式不对）原有 graph 保持不动，只
    把错误原样返回给前端，绝不用半成品或猜测的内容覆盖专家已经确认过的图。
    """
    record = db.get(workflow_id)
    if not record:
        raise HTTPException(status_code=404, detail="workflow not found")
    check = _regenerate_check(record)
    if not check.allowed:
        raise HTTPException(status_code=409, detail=check.reason)

    try:
        new_graph = guide_service.regenerate_graph_from_transcript(record["turns"])
    except llm_client.LLMError as e:
        raise HTTPException(status_code=502, detail=f"重新生成流程图失败：{e}") from e

    issues = graph_validator.validate(new_graph)
    if any(i["level"] == "error" for i in issues):
        raise HTTPException(
            status_code=422,
            detail={"message": "模型重新生成的流程图未通过结构校验，原有流程图未改动", "issues": issues},
        )

    record["graph"] = new_graph
    record["validation"] = issues

    if record.get("_review"):
        result = review_agent.after_regeneration(record["_review"], new_graph)
        record["turns"].append(_review_turn(result))
        record["status"] = "collecting"
        _apply_review_state(record, result.state)
        record["updated_at"] = _now()
        db.save(record)
        return WorkflowRecord.model_validate(_strip_internal(record, in_dataset=False))

    # Reset the conversation progress to match the new graph: the old guide state (cursor,
    # sweep chip options, pending branch/correction scratch) points at node ids that no longer
    # exist. guide_service picks up from the structural sweeps on the new graph instead.
    old_state = record.get("_guide_state") or {"stage": record["stage"], "cursor": None, "pending": {}}
    reply, next_question, new_state = guide_service.state_after_regeneration(old_state, new_graph)
    record["_guide_state"] = new_state
    record["stage"] = new_state["stage"]
    record["case_context"] = new_state.get("pending", {}).get("case_context")
    record["unresolved"] = [next_question] if next_question else []
    record["turns"].append(_assistant_turn(reply, next_question))
    # Per-turn rollback snapshots hold pre-refresh graphs -- rolling back across the refresh
    # would silently swap the old graph back in, so the correction picker starts fresh here.
    record["_turn_state_log"] = []

    # A regenerated graph is unconfirmed by construction -- even if the workflow was already
    # expert_confirmed, the expert hasn't looked at *this* graph yet. Ready for confirmation
    # only once the remaining questions are done (same rule as post_turn).
    ready = new_state["stage"] == "review" and not any(i["level"] == "error" for i in issues)
    record["completion"] = {"score": _completion_score(record), "ready_for_confirmation": ready}
    record["status"] = "needs_confirmation" if ready else "collecting"
    record["updated_at"] = _now()
    db.save(record)
    return WorkflowRecord.model_validate(_strip_internal(record, in_dataset=False))
