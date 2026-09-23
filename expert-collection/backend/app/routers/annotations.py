"""Prior + Gold annotation endpoints -- design/case_context_and_prior_annotation_draft.md
section 2, IMPLEMENTATION_PLAN.md section 9.2 (Prior, Phase 7) and section 9 §9 Phase C-2
(Gold, this round). Two layers on the same underlying data:

- **Prior** (`prior_status`, unchanged since Phase 7): "Public/LLM-derived Prior" becomes
  "Expert-annotated Prior" the moment ANY annotation exists -- quick quality screening, one
  pass is enough. Still only meaningful for `public_extracted` (an expert_collected record
  isn't an unreviewed "candidate" the way an import is).
- **Gold** (`gold_status`, new): a stricter bar requiring two *independent* annotations that
  agree, or a third person's arbitration when they don't (IMPLEMENTATION_PLAN.md section 9's
  four confirmed decisions). Applies to both source types -- an expert_collected record's own
  `expert_confirmed` flag is self-attested, not independently verified, so it doesn't imply
  Gold on its own either.

Without a real account system, "independent" can only be enforced by requiring a
free-text `annotator_name` on every submission and checking it differs from whoever annotated
this record before -- an honest, lightweight identity proxy (same spirit as `actor_role`
elsewhere in this codebase), not real auth. See IMPLEMENTATION_PLAN.md section 9 for the
limitation this implies.

`based_on_annotation_id` keeps pointing at whatever annotation immediately preceded this one
in time (for chronological display), but no longer means "supersedes" the way it did when
this was a single-annotator chain -- gold_status is computed by role_in_process, not by chain
position. dataset_versions rows themselves are never mutated -- annotation state is always
derived by joining against prior_annotations, so a published version stays immutable.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from .. import dataset_records, db, gold_annotation
from ..models import (
    AnnotationSummary,
    CreateAnnotationRequest,
    PriorAnnotation,
    PriorRecordDetail,
    PriorRecordSummary,
)

router = APIRouter(prefix="/api/datasets/versions/{version_id}", tags=["prior-annotations"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


_compute_gold_status = gold_annotation.compute_gold_status
_cohens_kappa = gold_annotation.cohens_kappa


@router.get("/records", response_model=list[PriorRecordSummary])
def list_records(version_id: str) -> list[PriorRecordSummary]:
    version = _get_annotatable_version(version_id)
    latest_by_record = {a["record_id"]: a for a in db.list_annotations_for_version(version_id)}
    out = []
    for r in dataset_records.records_for_export(version):
        rid = r.get("record_id")
        latest = latest_by_record.get(rid)
        history = db.list_annotations(version_id, rid)
        out.append(PriorRecordSummary(
            record_id=rid,
            name=r.get("scenario", {}).get("scenario_name") or rid,
            node_count=len(r.get("graph", {}).get("nodes", [])),
            prior_status="expert_annotated" if latest else "raw",
            latest_verdict=latest["verdict"] if latest else None,
            gold_status=_compute_gold_status(history),
        ))
    return out


@router.get("/records/{record_id}", response_model=PriorRecordDetail)
def get_record(version_id: str, record_id: str) -> PriorRecordDetail:
    version = _get_annotatable_version(version_id)
    record = _find_record(version, record_id)
    history = db.list_annotations(version_id, record_id)
    return PriorRecordDetail(
        record_id=record_id,
        name=record.get("scenario", {}).get("scenario_name") or record_id,
        graph=record["graph"],
        prior_status="expert_annotated" if history else "raw",
        gold_status=_compute_gold_status(history),
        annotations=[PriorAnnotation(**a) for a in history],
    )


@router.post("/records/{record_id}/annotations", response_model=PriorRecordDetail)
def create_annotation(version_id: str, record_id: str, req: CreateAnnotationRequest) -> PriorRecordDetail:
    version = _get_annotatable_version(version_id)
    record = _find_record(version, record_id)

    name = req.annotator_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="标注人姓名不能为空")

    history = db.list_annotations(version_id, record_id)
    independents = [a for a in history if a.get("role_in_process", "independent") == "independent"]
    arbitrations = [a for a in history if a.get("role_in_process") == "arbitration"]

    if arbitrations:
        raise HTTPException(status_code=400, detail="这条记录已经完成仲裁，标注流程已结束")
    if len(independents) >= 2:
        if independents[0]["verdict"] == independents[1]["verdict"]:
            raise HTTPException(status_code=400, detail="这条记录已经有两次一致的独立标注，无需仲裁")
        prior_names = {independents[0]["annotator_name"].strip().lower(), independents[1]["annotator_name"].strip().lower()}
        if name.lower() in prior_names:
            raise HTTPException(status_code=400, detail="仲裁人不能是之前两次独立标注中的任何一位")
        role_in_process = "arbitration"
    elif len(independents) == 1:
        if independents[0]["annotator_name"].strip().lower() == name.lower():
            raise HTTPException(
                status_code=400,
                detail=f"第二次独立标注需要换一个人，不能跟上一次的标注人「{independents[0]['annotator_name']}」相同",
            )
        role_in_process = "independent"
    else:
        role_in_process = "independent"

    previous = db.latest_annotation(version_id, record_id)
    entry = {
        "annotation_id": uuid.uuid4().hex[:10],
        "version_id": version_id,
        "record_id": record_id,
        "based_on_annotation_id": previous["annotation_id"] if previous else None,
        "verdict": req.verdict,
        "node_verdicts": req.node_verdicts,
        "note": req.note,
        "actor_role": req.actor_role,
        "annotator_name": name,
        "role_in_process": role_in_process,
        "annotated_at": _now(),
    }
    db.save_annotation(entry)

    history = db.list_annotations(version_id, record_id)
    return PriorRecordDetail(
        record_id=record_id,
        name=record.get("scenario", {}).get("scenario_name") or record_id,
        graph=record["graph"],
        prior_status="expert_annotated",
        gold_status=_compute_gold_status(history),
        annotations=[PriorAnnotation(**a) for a in history],
    )


@router.get("/annotation-summary", response_model=AnnotationSummary)
def annotation_summary(version_id: str) -> AnnotationSummary:
    version = _get_annotatable_version(version_id)
    total = len(dataset_records.records_for_export(version))
    latest = db.list_annotations_for_version(version_id)
    verdict_counts: dict[str, int] = {}
    for a in latest:
        verdict_counts[a["verdict"]] = verdict_counts.get(a["verdict"], 0) + 1

    gold_counts: dict[str, int] = {}
    kappa_pairs: list[tuple[str, str]] = []
    for r in dataset_records.records_for_export(version):
        history = db.list_annotations(version_id, r["record_id"])
        status = _compute_gold_status(history)
        gold_counts[status] = gold_counts.get(status, 0) + 1
        independents = [a for a in history if a.get("role_in_process", "independent") == "independent"]
        if len(independents) >= 2:
            kappa_pairs.append((independents[0]["verdict"], independents[1]["verdict"]))

    return AnnotationSummary(
        version_id=version_id, total_records=total,
        annotated_records=len(latest), verdict_counts=verdict_counts,
        gold_counts=gold_counts, agreement_kappa=_cohens_kappa(kappa_pairs),
    )
