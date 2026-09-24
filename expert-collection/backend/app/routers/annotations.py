"""Prior + Gold annotation endpoints -- design/case_context_and_prior_annotation_draft.md
section 2, IMPLEMENTATION_PLAN.md section 9.2 (Prior, Phase 7), section 9 §9 Phase C-2 (Gold)
and section 15 (blind review, structured reasons, Rework loop). Layers on the same data:

- **Prior** (`prior_status`): "Public/LLM-derived Prior" becomes "Expert-annotated Prior" the
  moment ANY annotation exists.
- **Gold** (`gold_status`/`stage`, computed in gold_annotation.py): every record gets two
  *independent* annotations per round (decision 8: full double annotation, not sampled), a
  third person's arbitration when they disagree, and -- when a round settles on
  "needs_revision" -- a Rework step that produces a corrected graph and opens the next round
  (decision 9).

Blind review: while a record is in independent review, the detail/list endpoints don't
return anyone's verdict, notes or node verdicts (the first annotator's conclusion anchoring
the second was the flaw this fixes). Names of who already annotated this round ARE returned
-- the UI needs them to stop the same person annotating twice before they do the work.

Without a real account system, "independent" is enforced by the free-text `annotator_name`
(an honest, lightweight identity proxy, same as before -- see IMPLEMENTATION_PLAN.md section 9).

dataset_versions rows are never mutated: annotations and rework revisions live in their own
tables keyed by (version_id, record_id), and the current graph is derived at read time.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from .. import annotation_signals, audit, dataset_records, db, gold_annotation, graph_validator, rework
from ..models import (
    AnnotationSummary,
    CreateAnnotationRequest,
    CreateReworkRequest,
    PriorAnnotation,
    PriorRecordDetail,
    PriorRecordSummary,
    RecordRevision,
    ReworkEdits,
    ReworkPreviewResponse,
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


def _check_round(requested: int | None, state: dict) -> None:
    if requested is not None and requested != state["round"]:
        raise HTTPException(status_code=409, detail="这条记录已进入新的一轮（有人提交了返工），请刷新后重新查看")


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
    version = _get_annotatable_version(version_id)
    record = _find_record(version, record_id)

    name = req.annotator_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="标注人姓名不能为空")

    history = db.list_annotations(version_id, record_id)
    revisions = db.list_revisions(version_id, record_id)
    state = gold_annotation.compute_state(history, revisions)
    _check_round(req.round, state)
    stage = state["stage"]

    if stage == "done":
        raise HTTPException(status_code=400, detail="这条记录本轮已有结论，标注流程已结束")
    if stage == "rework":
        raise HTTPException(status_code=400, detail="这条记录本轮结论是「需要修改」，正在等待返工，返工提交后才能开始下一轮标注")

    names, reworker = _round_people(state, revisions)
    if reworker and _norm(reworker) == _norm(name):
        raise HTTPException(status_code=400, detail=f"「{reworker}」是本轮修正图的返工人，不能复核自己的返工")
    independents = [a for a in state["round_annotations"] if a.get("role_in_process", "independent") == "independent"]
    if stage == "arbitration":
        if _norm(name) in {_norm(a["annotator_name"]) for a in independents[:2]}:
            raise HTTPException(status_code=400, detail="仲裁人不能是本轮两次独立标注中的任何一位")
        role_in_process = "arbitration"
    else:
        if stage == "second_review" and _norm(independents[0]["annotator_name"]) == _norm(name):
            raise HTTPException(
                status_code=400,
                detail=f"第二次独立标注需要换一个人，不能跟本轮第一位标注人「{independents[0]['annotator_name']}」相同",
            )
        role_in_process = "independent"

    # Structured reasons (decision 10): required for anything other than "accepted".
    tags = list(dict.fromkeys(req.reason_tags))  # dedupe, keep order
    note = (req.note or "").strip() or None
    if req.verdict == "accepted":
        tags = []
    else:
        if not tags:
            raise HTTPException(status_code=400, detail="选择「需要修改」或「丢弃」时，至少要勾选一个原因标签")
        if "other" in tags and not note:
            raise HTTPException(status_code=400, detail="勾选了「其他」原因时，请在备注里写明具体原因")

    # Node verdicts only mean something for "needs_revision"; they must be applicable to the
    # current graph so the reworker can start from them as-is.
    node_verdicts = {k: v for k, v in req.node_verdicts.items() if v != "keep"} if req.verdict == "needs_revision" else {}
    graph = _current_graph(record, revisions)
    try:
        rework.validate_edits(graph, {"node_verdicts": node_verdicts})
    except rework.EditError as e:
        raise HTTPException(status_code=400, detail=str(e))

    previous = history[-1] if history else None
    entry = {
        "annotation_id": uuid.uuid4().hex[:10],
        "version_id": version_id,
        "record_id": record_id,
        "based_on_annotation_id": previous["annotation_id"] if previous else None,
        "verdict": req.verdict,
        "node_verdicts": node_verdicts,
        "reason_tags": tags,
        "note": note,
        "actor_role": req.actor_role,
        "annotator_name": name,
        "role_in_process": role_in_process,
        "round": state["round"],
        "annotated_at": _now(),
    }
    db.save_annotation(entry)
    return _detail(version, record, db.list_annotations(version_id, record_id), revisions)


def _apply_or_400(graph: dict, edits: ReworkEdits, new_node_prefix: str) -> dict:
    try:
        return rework.apply_edits(graph, edits.model_dump(), new_node_prefix=new_node_prefix)
    except rework.EditError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/records/{record_id}/rework/preview", response_model=ReworkPreviewResponse)
def preview_rework(version_id: str, record_id: str, edits: ReworkEdits) -> ReworkPreviewResponse:
    """Applies edits to the current graph without saving -- the Rework editor's live preview.
    Same code path as the real submission, so what's previewed is exactly what gets saved.
    """
    version = _get_annotatable_version(version_id)
    record = _find_record(version, record_id)
    revisions = db.list_revisions(version_id, record_id)
    state = gold_annotation.compute_state(db.list_annotations(version_id, record_id), revisions)
    graph = _apply_or_400(_current_graph(record, revisions), edits, f"r{state['round'] + 1}_n")
    return ReworkPreviewResponse(graph=graph, issues=graph_validator.validate(graph))


@router.post("/records/{record_id}/rework", response_model=PriorRecordDetail)
def create_rework(version_id: str, record_id: str, req: CreateReworkRequest) -> PriorRecordDetail:
    version = _get_annotatable_version(version_id)
    record = _find_record(version, record_id)
    name = req.reworker_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="返工人姓名不能为空")

    history = db.list_annotations(version_id, record_id)
    revisions = db.list_revisions(version_id, record_id)
    state = gold_annotation.compute_state(history, revisions)
    _check_round(req.round, state)
    if state["stage"] != "rework":
        raise HTTPException(status_code=400, detail="只有本轮结论为「需要修改」的记录才能提交返工")

    edits = req.edits
    has_change = any(v != "keep" for v in edits.node_verdicts.values()) or edits.renames or edits.inserts
    if not has_change:
        raise HTTPException(status_code=400, detail="返工没有做任何修改")

    graph = _apply_or_400(_current_graph(record, revisions), edits, f"r{state['round'] + 1}_n")
    errors = [i for i in graph_validator.validate(graph) if i["level"] == "error"]
    if errors:
        raise HTTPException(status_code=400, detail="修正后的图结构不合法：" + "；".join(i["message"] for i in errors))

    entry = {
        "revision_id": uuid.uuid4().hex[:10],
        "version_id": version_id,
        "record_id": record_id,
        "from_round": state["round"],
        "edits": edits.model_dump(),
        "graph": graph,
        "reworker_name": name,
        "note": (req.note or "").strip() or None,
        "actor_role": req.actor_role,
        "created_at": _now(),
    }
    db.save_revision(entry)
    audit.log(req.actor_role or "unknown", "record_rework", {
        "dataset_version_id": version_id, "record_id": record_id,
        "revision_id": entry["revision_id"], "from_round": state["round"], "reworker_name": name,
    })
    return _detail(version, record, history, db.list_revisions(version_id, record_id))


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
    rework_count = 0
    for r in records:
        rid = r["record_id"]
        history = annotations.get(rid, [])
        revs = revisions.get(rid, [])
        rework_count += len(revs)
        state = gold_annotation.compute_state(history, revs)
        gold_counts[state["gold_status"]] = gold_counts.get(state["gold_status"], 0) + 1
        stage_counts[state["stage"]] = stage_counts.get(state["stage"], 0) + 1
        pairs.extend(gold_annotation.kappa_pairs(history))
        # Only settled rounds count toward verdict/reason distributions -- past rounds are
        # settled by definition (a revision exists), plus the current round when it's done
        # or waiting for rework. An open round's verdicts would leak through the aggregates.
        current_open = state["stage"] not in ("done", "rework")
        for rnd in range(1, state["round"] + 1):
            if rnd == state["round"] and current_open:
                continue
            in_round = [a for a in history if int(a.get("round") or 1) == rnd]
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
        rework_count=rework_count,
    )
