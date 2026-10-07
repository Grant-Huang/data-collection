"""Prior + Gold annotation endpoints -- design/case_context_and_prior_annotation_draft.md
section 2, IMPLEMENTATION_PLAN.md section 9.2 (Prior), section 9 §9 Phase C-2 (Gold), section
16 (blind review, structured reasons) and section 17 (annotation on the review loop):

- **Prior** (`prior_status`): "Public/LLM-derived Prior" becomes "Expert-annotated Prior" the
  moment ANY annotation exists.
- **Gold** (`gold_status`/`stage`, computed in gold_annotation.py): two *independent*
  annotations per record (full double annotation), a third person's arbitration when they
  disagree. Section 17: each annotator reviews the record in a conversation
  (review_agent, mode "annotate"/"arbitrate") and corrects the graph there; confirming at the
  end writes one annotation carrying the verdict, reason tags, the list of changes and -- for
  needs_revision -- the corrected graph. There is no separate rework step any more.

Blind review: while a record is in independent review, the detail/list endpoints don't return
anyone's verdict, notes or corrections, and each review session only contains its own
annotator's messages and working graph. Names of who already annotated this round ARE
returned -- the UI needs them to stop the same person annotating twice before they do the
work.

Without a real account system, "independent" is enforced by the free-text `annotator_name`
(an honest, lightweight identity proxy -- see IMPLEMENTATION_PLAN.md section 9).

dataset_versions rows are never mutated: annotations, sessions and legacy rework revisions
live in their own tables keyed by (version_id, record_id); state is derived at read time.
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from .. import annotation_signals, dataset_records, db, gold_annotation, review_agent
from ..models import (
    AnnotationSummary,
    CreateAnnotationRequest,
    PriorAnnotation,
    PriorRecordDetail,
    PriorRecordSummary,
    RecordRevision,
    ReviewSession,
    ReviewSessionTurnRequest,
    StartReviewSessionRequest,
)
from .datasets import _thresholds

router = APIRouter(prefix="/api/datasets/versions/{version_id}", tags=["prior-annotations"])

_BLIND_STAGES = ("first_review", "second_review")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(name: str) -> str:
    return name.strip().lower()


def _get_annotatable_version(version_id: str) -> dict:
    version = db.get_dataset_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="dataset version not found")
    if version["source_type"] not in ("public_extracted", "expert_collected"):
        raise HTTPException(status_code=404, detail="该数据来源不支持标注")
    return version


def _find_record(version: dict, record_id: str) -> dict:
    for r in dataset_records.records_for_export(version):
        if r.get("record_id") == record_id:
            return r
    raise HTTPException(status_code=404, detail="record not found in this version")


def _record_name(record: dict) -> str:
    return (record.get("scenario") or {}).get("scenario_name") or record["record_id"]


def _current_graph(record: dict, revisions: list[dict]) -> dict:
    return revisions[-1]["graph"] if revisions else record["graph"]


def _round_people(state: dict, revisions: list[dict]) -> tuple[list[str], str | None]:
    names = [a["annotator_name"] for a in state["round_annotations"]]
    reworker = revisions[-1]["reworker_name"] if revisions else None
    return names, reworker


def _revision_model(r: dict) -> RecordRevision:
    return RecordRevision(**{k: v for k, v in r.items() if k in RecordRevision.model_fields})


def _signals(version: dict, records: list[dict], record_id: str, graph: dict) -> list[dict]:
    text_th, struct_th = _thresholds()
    by_record = annotation_signals.version_signals(version, records, text_th, struct_th)
    return annotation_signals.graph_signals(graph) + by_record.get(record_id, [])


def _detail(version: dict, record: dict, history: list[dict], revisions: list[dict]) -> PriorRecordDetail:
    state = gold_annotation.compute_state(history, revisions)
    graph = _current_graph(record, revisions)
    names, reworker = _round_people(state, revisions)
    blind = state["stage"] in _BLIND_STAGES
    records = dataset_records.records_for_export(version)
    return PriorRecordDetail(
        record_id=record["record_id"],
        name=_record_name(record),
        graph=graph,
        original_graph=record["graph"],
        final_graph=state["final_graph"],
        prior_status="expert_annotated" if history else "raw",
        gold_status=state["gold_status"],
        stage=state["stage"],
        round=state["round"],
        blind=blind,
        round_annotator_names=names,
        round_reworker_name=reworker,
        annotation_count=len(history),
        annotations=[] if blind else [PriorAnnotation(**a) for a in history],
        revisions=[] if blind else [_revision_model(r) for r in revisions],
        final_verdict=state["outcome"] if state["stage"] == "done" else None,
        signals=_signals(version, records, record["record_id"], graph),
    )


def _role_for(state: dict, reworker: str | None, name: str) -> str:
    """Who may annotate now, as whom. Raises 400 with a message the UI shows as-is."""
    stage = state["stage"]
    if stage == "done":
        raise HTTPException(status_code=400, detail="这条记录已经有结论，标注流程已结束")
    if reworker and _norm(reworker) == _norm(name):
        raise HTTPException(status_code=400, detail=f"「{reworker}」是本轮修正图的返工人，不能复核自己的返工")
    independents = [a for a in state["round_annotations"] if a.get("role_in_process", "independent") == "independent"]
    if stage == "arbitration":
        if _norm(name) in {_norm(a["annotator_name"]) for a in independents[:2]}:
            raise HTTPException(status_code=400, detail="仲裁人不能是本轮两次独立标注中的任何一位")
        return "arbitration"
    if stage == "second_review" and _norm(independents[0]["annotator_name"]) == _norm(name):
        raise HTTPException(
            status_code=400,
            detail=f"第二次独立标注需要换一个人，不能跟本轮第一位标注人「{independents[0]['annotator_name']}」相同",
        )
    return "independent"


def _save_annotation(version_id: str, record_id: str, history: list[dict], *, verdict: str, reason_tags: list[str],
                     note: str | None, name: str, role: str, round_: int, actor_role: str | None,
                     revised_graph: dict | None = None, changes: list[str] | None = None,
                     session_id: str | None = None) -> dict:
    entry = {
        "annotation_id": uuid.uuid4().hex[:10],
        "version_id": version_id,
        "record_id": record_id,
        "based_on_annotation_id": history[-1]["annotation_id"] if history else None,
        "verdict": verdict,
        "node_verdicts": {},
        "reason_tags": reason_tags,
        "note": note,
        "actor_role": actor_role,
        "annotator_name": name,
        "role_in_process": role,
        "round": round_,
        "annotated_at": _now(),
        "revised_graph": revised_graph,
        "changes": changes or [],
        "session_id": session_id,
    }
    db.save_annotation(entry)
    return entry


@router.get("/records", response_model=list[PriorRecordSummary])
def list_records(version_id: str) -> list[PriorRecordSummary]:
    version = _get_annotatable_version(version_id)
    records = dataset_records.records_for_export(version)
    annotations = db.list_annotations_by_record(version_id)
    revisions = db.list_revisions_by_record(version_id)
    text_th, struct_th = _thresholds()
    by_record_signals = annotation_signals.version_signals(version, records, text_th, struct_th)
    out = []
    for r in records:
        rid = r.get("record_id")
        history = annotations.get(rid, [])
        revs = revisions.get(rid, [])
        state = gold_annotation.compute_state(history, revs)
        graph = _current_graph(r, revs)
        names, reworker = _round_people(state, revs)
        signals = annotation_signals.graph_signals(graph) + by_record_signals.get(rid, [])
        out.append(PriorRecordSummary(
            record_id=rid,
            name=_record_name(r),
            node_count=len(graph.get("nodes", [])),
            prior_status="expert_annotated" if history else "raw",
            final_verdict=state["outcome"] if state["stage"] == "done" else None,
            gold_status=state["gold_status"],
            stage=state["stage"],
            round=state["round"],
            round_annotator_names=names,
            round_reworker_name=reworker,
            signal_error_count=sum(1 for s in signals if s["level"] == "error"),
            signal_warning_count=sum(1 for s in signals if s["level"] == "warning"),
        ))
    return out


@router.get("/records/{record_id}", response_model=PriorRecordDetail)
def get_record(version_id: str, record_id: str) -> PriorRecordDetail:
    version = _get_annotatable_version(version_id)
    record = _find_record(version, record_id)
    return _detail(version, record, db.list_annotations(version_id, record_id), db.list_revisions(version_id, record_id))


@router.post("/records/{record_id}/annotations", response_model=PriorRecordDetail)
def create_annotation(version_id: str, record_id: str, req: CreateAnnotationRequest) -> PriorRecordDetail:
    """Direct verdict without a conversation (kept for API clients / scripts). The UI uses the
    review session below. A needs_revision submitted here has no corrected graph, so on its
    own it can't settle a record -- the round goes to arbitration, where the arbitrator makes
    the correction in conversation."""
    version = _get_annotatable_version(version_id)
    record = _find_record(version, record_id)
    name = req.annotator_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="标注人姓名不能为空")

    history = db.list_annotations(version_id, record_id)
    revisions = db.list_revisions(version_id, record_id)
    state = gold_annotation.compute_state(history, revisions)
    if req.round is not None and req.round != state["round"]:
        raise HTTPException(status_code=409, detail="这条记录的状态已经变化，请刷新后重新查看")
    _, reworker = _round_people(state, revisions)
    role = _role_for(state, reworker, name)

    tags = list(dict.fromkeys(req.reason_tags))
    note = (req.note or "").strip() or None
    if req.verdict == "accepted":
        tags = []
    else:
        if not tags:
            raise HTTPException(status_code=400, detail="选择「需要修改」或「丢弃」时，至少要勾选一个原因标签")
        if "other" in tags and not note:
            raise HTTPException(status_code=400, detail="勾选了「其他」原因时，请在备注里写明具体原因")

    _save_annotation(version_id, record_id, history, verdict=req.verdict, reason_tags=tags, note=note, name=name,
                     role=role, round_=state["round"], actor_role=req.actor_role)
    return _detail(version, record, db.list_annotations(version_id, record_id), revisions)


# --- review sessions (section 17.4) --------------------------------------------------------

def _session_model(s: dict) -> ReviewSession:
    return ReviewSession(
        session_id=s["session_id"], version_id=s["version_id"], record_id=s["record_id"],
        annotator_name=s["annotator_name"], role_in_process=s["role_in_process"], round=s["round"],
        phase=s["review"]["phase"], status=s["status"], graph=s["graph"], base_graph=s["base_graph"],
        turns=s["turns"], proposal=s["review"].get("proposal"), annotation_id=s.get("annotation_id"),
    )


def _assistant_turn(result: review_agent.TurnResult) -> dict:
    return {"turn_id": uuid.uuid4().hex[:8], "role": "assistant", "text": result.text, "ack": result.ack,
            "question": result.question, "changes": result.changes or None, "body": result.body}


def _candidates(state: dict) -> list[dict]:
    """What the arbitrator gets to see: each independent annotator's verdict, reasons, change
    list and corrected graph (arbitration isn't blind)."""
    out = []
    for a in [x for x in state["round_annotations"] if x.get("role_in_process", "independent") == "independent"][:2]:
        out.append({"annotation_id": a["annotation_id"], "annotator_name": a["annotator_name"], "verdict": a["verdict"],
                    "reason_tags": a.get("reason_tags", []), "changes": a.get("changes", []),
                    "revised_graph": a.get("revised_graph")})
    return out


@router.post("/records/{record_id}/review-session", response_model=ReviewSession)
def start_review_session(version_id: str, record_id: str, req: StartReviewSessionRequest) -> ReviewSession:
    """Start -- or resume, if this annotator already has an unfinished one for this round --
    a review conversation on the record."""
    version = _get_annotatable_version(version_id)
    record = _find_record(version, record_id)
    name = req.annotator_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="标注人姓名不能为空")
    history = db.list_annotations(version_id, record_id)
    revisions = db.list_revisions(version_id, record_id)
    state = gold_annotation.compute_state(history, revisions)
    _, reworker = _round_people(state, revisions)
    role = _role_for(state, reworker, name)

    for s in db.list_review_sessions(version_id, record_id):
        if (s["status"] == "active" and _norm(s["annotator_name"]) == _norm(name)
                and s["round"] == state["round"] and s["role_in_process"] == role):
            return _session_model(s)

    graph = copy.deepcopy(_current_graph(record, revisions))
    mode = "arbitrate" if role == "arbitration" else "annotate"
    review = review_agent.new_state(mode, base_graph=copy.deepcopy(graph),
                                    candidates=_candidates(state) if mode == "arbitrate" else None)
    opening = review_agent.opening(review, graph)
    now = _now()
    session = {
        "session_id": uuid.uuid4().hex[:12], "version_id": version_id, "record_id": record_id,
        "annotator_name": name, "role_in_process": role, "round": state["round"], "status": "active",
        "graph": graph, "base_graph": copy.deepcopy(graph), "turns": [_assistant_turn(opening)],
        "review": opening.state, "annotation_id": None, "actor_role": req.actor_role,
        "created_at": now, "updated_at": now,
    }
    db.save_review_session(session)
    return _session_model(session)


def _load_session(version_id: str, session_id: str) -> dict:
    s = db.get_review_session(session_id)
    if not s or s["version_id"] != version_id:
        raise HTTPException(status_code=404, detail="review session not found")
    return s


@router.get("/review-sessions/{session_id}", response_model=ReviewSession)
def get_review_session(version_id: str, session_id: str) -> ReviewSession:
    return _session_model(_load_session(version_id, session_id))


@router.post("/review-sessions/{session_id}/turns", response_model=ReviewSession)
def review_session_turn(version_id: str, session_id: str, req: ReviewSessionTurnRequest) -> ReviewSession:
    session = _load_session(version_id, session_id)
    if session["status"] != "active":
        raise HTTPException(status_code=409, detail="这次标注已经提交或已失效")
    version = _get_annotatable_version(version_id)
    record = _find_record(version, session["record_id"])
    history = db.list_annotations(version_id, session["record_id"])
    revisions = db.list_revisions(version_id, session["record_id"])
    state = gold_annotation.compute_state(history, revisions)
    _, reworker = _round_people(state, revisions)
    # The record may have moved on while this conversation was open (e.g. someone else
    # finished the arbitration) -- then this session can't be submitted any more.
    try:
        role = _role_for(state, reworker, session["annotator_name"])
    except HTTPException as e:
        session["status"] = "stale"
        db.save_review_session(session)
        raise HTTPException(status_code=409, detail=f"这条记录的状态已经变化：{e.detail}") from e
    if state["round"] != session["round"] or role != session["role_in_process"]:
        session["status"] = "stale"
        db.save_review_session(session)
        raise HTTPException(status_code=409, detail="这条记录的状态已经变化，这次标注已失效，请重新打开")

    turn_id = uuid.uuid4().hex[:8]
    person_turn = {"turn_id": turn_id, "role": "expert", "text": req.text}
    if req.raw_transcript:
        person_turn["raw_transcript"] = req.raw_transcript
    session["turns"].append(person_turn)

    result = review_agent.handle_turn(session["review"], session["graph"], session["turns"], req.text, turn_id)
    if result.graph is not None:
        session["graph"] = result.graph
    session["review"] = result.state
    session["turns"].append(_assistant_turn(result))

    if result.finished:
        proposal = result.state.get("proposal") or review_agent.propose_verdict(result.state, session["graph"], rejected=False)
        changes, _ = review_agent.describe_changes(session["base_graph"], session["graph"])
        entry = _save_annotation(
            version_id, session["record_id"], history, verdict=proposal["verdict"], reason_tags=proposal["reason_tags"],
            note="；".join(changes) or None, name=session["annotator_name"], role=role, round_=state["round"],
            actor_role=session.get("actor_role"),
            revised_graph=session["graph"] if proposal["verdict"] == "needs_revision" else None,
            changes=changes, session_id=session_id,
        )
        session["status"] = "submitted"
        session["annotation_id"] = entry["annotation_id"]
    session["updated_at"] = _now()
    db.save_review_session(session)
    return _session_model(session)


@router.get("/annotation-summary", response_model=AnnotationSummary)
def annotation_summary(version_id: str) -> AnnotationSummary:
    version = _get_annotatable_version(version_id)
    records = dataset_records.records_for_export(version)
    annotations = db.list_annotations_by_record(version_id)
    revisions = db.list_revisions_by_record(version_id)

    verdict_counts: dict[str, int] = {}
    gold_counts: dict[str, int] = {}
    stage_counts: dict[str, int] = {}
    reason_tag_counts: dict[str, int] = {}
    pairs: list[tuple[str, str]] = []
    corrected = 0
    for r in records:
        rid = r["record_id"]
        history = annotations.get(rid, [])
        revs = revisions.get(rid, [])
        state = gold_annotation.compute_state(history, revs)
        gold_counts[state["gold_status"]] = gold_counts.get(state["gold_status"], 0) + 1
        stage_counts[state["stage"]] = stage_counts.get(state["stage"], 0) + 1
        pairs.extend(gold_annotation.kappa_pairs(history))
        if state["final_graph"]:
            corrected += 1
        # Only settled rounds count toward verdict/reason distributions (an open round's
        # verdicts would leak through the aggregates): legacy past rounds, plus the current
        # round once it's done.
        for rnd in range(1, state["round"] + 1):
            in_round = [a for a in history if int(a.get("round") or 1) == rnd]
            if rnd == state["round"]:
                if state["stage"] != "done":
                    continue
                outcome = state["outcome"]
            else:
                outcome = gold_annotation.round_outcome(in_round)
            if outcome:
                verdict_counts[outcome] = verdict_counts.get(outcome, 0) + 1
            for a in in_round:
                for t in a.get("reason_tags") or []:
                    reason_tag_counts[t] = reason_tag_counts.get(t, 0) + 1

    return AnnotationSummary(
        version_id=version_id, total_records=len(records),
        annotated_records=sum(1 for r in records if annotations.get(r["record_id"])),
        verdict_counts=verdict_counts, gold_counts=gold_counts, stage_counts=stage_counts,
        reason_tag_counts=reason_tag_counts, agreement_kappa=gold_annotation.cohens_kappa(pairs),
        corrected_count=corrected,
    )
