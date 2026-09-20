"""Prior annotation endpoints -- design/case_context_and_prior_annotation_draft.md section 2,
IMPLEMENTATION_PLAN.md section 9.2. "Public/LLM-derived Prior" (an imported public_extracted
record nobody has reviewed) becomes "Expert-annotated Prior" once at least one annotation
exists for it. Only public_extracted versions are in scope -- LLM-integrated workflows go
through the same import pipeline as everything else (design draft decision 4), so there is
no separate code path for them here.

Annotations are a single chain per (version_id, record_id), not independent per-annotator
rows (design draft decision 3): each new annotation is recorded against whatever the current
latest one is, and the UI is expected to prefill from that latest verdict rather than start
blank. dataset_versions rows themselves are never mutated -- annotation state is always
derived by joining against prior_annotations, so a published version stays immutable.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from .. import db
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


def _get_public_version(version_id: str) -> dict:
    version = db.get_dataset_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="dataset version not found")
    if version["source_type"] != "public_extracted":
        # Annotation only makes sense for imported/LLM-derived candidate data -- expert_collected
        # records go through the conversational confirm flow instead, they don't need this.
        raise HTTPException(status_code=404, detail="该版本不是 public_extracted，没有 Prior 标注")
    return version


def _find_record(version: dict, record_id: str) -> dict:
    for r in version.get("records", []):
        if r.get("record_id") == record_id:
            return r
    raise HTTPException(status_code=404, detail="record not found in this version")


@router.get("/records", response_model=list[PriorRecordSummary])
def list_records(version_id: str) -> list[PriorRecordSummary]:
    version = _get_public_version(version_id)
    latest_by_record = {a["record_id"]: a for a in db.list_annotations_for_version(version_id)}
    out = []
    for r in version.get("records", []):
        rid = r.get("record_id")
        latest = latest_by_record.get(rid)
        out.append(PriorRecordSummary(
            record_id=rid,
            name=r.get("scenario", {}).get("scenario_name") or rid,
            node_count=len(r.get("graph", {}).get("nodes", [])),
            prior_status="expert_annotated" if latest else "raw",
            latest_verdict=latest["verdict"] if latest else None,
        ))
    return out


@router.get("/records/{record_id}", response_model=PriorRecordDetail)
def get_record(version_id: str, record_id: str) -> PriorRecordDetail:
    version = _get_public_version(version_id)
    record = _find_record(version, record_id)
    history = db.list_annotations(version_id, record_id)
    return PriorRecordDetail(
        record_id=record_id,
        name=record.get("scenario", {}).get("scenario_name") or record_id,
        graph=record["graph"],
        prior_status="expert_annotated" if history else "raw",
        annotations=[PriorAnnotation(**a) for a in history],
    )


@router.post("/records/{record_id}/annotations", response_model=PriorRecordDetail)
def create_annotation(version_id: str, record_id: str, req: CreateAnnotationRequest) -> PriorRecordDetail:
    version = _get_public_version(version_id)
    record = _find_record(version, record_id)

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
        "annotated_at": _now(),
    }
    db.save_annotation(entry)

    history = db.list_annotations(version_id, record_id)
    return PriorRecordDetail(
        record_id=record_id,
        name=record.get("scenario", {}).get("scenario_name") or record_id,
        graph=record["graph"],
        prior_status="expert_annotated",
        annotations=[PriorAnnotation(**a) for a in history],
    )


@router.get("/annotation-summary", response_model=AnnotationSummary)
def annotation_summary(version_id: str) -> AnnotationSummary:
    version = _get_public_version(version_id)
    total = len(version.get("records", []))
    latest = db.list_annotations_for_version(version_id)
    verdict_counts: dict[str, int] = {}
    for a in latest:
        verdict_counts[a["verdict"]] = verdict_counts.get(a["verdict"], 0) + 1
    return AnnotationSummary(
        version_id=version_id, total_records=total,
        annotated_records=len(latest), verdict_counts=verdict_counts,
    )
