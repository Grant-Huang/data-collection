"""Dataset publish + Dashboard read endpoints -- PRD 12.0 (publish = snapshot the draft pool
into an immutable dataset_version) and 13 (Dashboard reads a version's readiness scores).
Phase 3 sub-scope only covers source_type=expert_collected (see IMPLEMENTATION_PLAN.md
section 6) -- public_extracted has no import pipeline yet, so its version list is just empty.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from .. import db, explain, quality, settings as settings_module
from ..models import DatasetVersionSummary, PublishDatasetRequest

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _published_workflow_ids(source_type: str) -> set[str]:
    ids: set[str] = set()
    for version in db.list_dataset_versions(source_type):
        ids.update(version["workflow_ids"])
    return ids


def _draft_pool(source_type: str) -> list[dict]:
    # Phase 3 sub-scope only wires up expert_collected -- every confirmed workflow record
    # *is* the expert_collected source, there's no separate ingestion step to distinguish.
    if source_type != "expert_collected":
        return []
    already_published = _published_workflow_ids(source_type)
    return [
        w for w in db.list_all()
        if w["status"] == "expert_confirmed" and w["id"] not in already_published
    ]


def _to_summary(version: dict) -> DatasetVersionSummary:
    readiness = version["readiness"]
    dims_with_explanations = {
        key: {**dim, "explanation": version["explanations"].get(key, "")}
        for key, dim in readiness["dimensions"].items()
    }
    return DatasetVersionSummary(
        id=version["id"],
        source_type=version["source_type"],
        version_number=version["version_number"],
        workflow_count=version["workflow_count"],
        total_steps=version["total_steps"],
        microflow_count=None,  # PRD 13.2: needs subgraph mining, not implemented this phase
        created_at=version["created_at"],
        readiness={**readiness, "dimensions": dims_with_explanations},
        archived=version.get("archived", False),
    )


@router.get("/draft-pool")
def get_draft_pool(source_type: str = "expert_collected") -> dict:
    pool = _draft_pool(source_type)
    return {"source_type": source_type, "count": len(pool)}


@router.post("/publish", response_model=DatasetVersionSummary)
def publish_dataset(req: PublishDatasetRequest) -> DatasetVersionSummary:
    pool = _draft_pool(req.source_type)
    if not pool:
        raise HTTPException(status_code=400, detail="草稿池为空，没有可发布的新记录")

    graphs = [w["graph"] for w in pool]
    min_sample_size = settings_module.get_effective_settings()["quality_params"]["min_sample_size"]
    readiness = quality.compute_readiness(graphs, min_sample_size=min_sample_size)
    explanations = explain.explain_all(readiness, pool)

    existing = db.list_dataset_versions(req.source_type)
    version_number = (max((v["version_number"] for v in existing), default=0)) + 1

    version = {
        "id": uuid.uuid4().hex[:12],
        "source_type": req.source_type,
        "name": req.name or req.source_type,
        "version_number": version_number,
        "workflow_ids": [w["id"] for w in pool],
        "workflow_count": len(pool),
        "total_steps": sum(len(g["nodes"]) for g in graphs),
        "readiness": readiness,
        "explanations": explanations,
        "created_at": _now(),
        "archived": False,
    }
    db.save_dataset_version(version)

    from .. import audit
    audit.log(req.actor_role or "unknown", "dataset_publish", {
        "dataset_version_id": version["id"], "source_type": req.source_type,
        "version_number": version_number, "workflow_count": len(pool),
    })

    return _to_summary(version)


@router.post("/versions/{version_id}/archive", response_model=DatasetVersionSummary)
def archive_version(version_id: str, actor_role: str = "unknown") -> DatasetVersionSummary:
    version = db.get_dataset_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="dataset version not found")
    db.archive_dataset_version(version_id)
    version["archived"] = True

    from .. import audit
    audit.log(actor_role, "dataset_archive", {"dataset_version_id": version_id})

    return _to_summary(version)


@router.get("/versions", response_model=list[DatasetVersionSummary])
def list_versions(source_type: str = "expert_collected", include_archived: bool = False) -> list[DatasetVersionSummary]:
    versions = db.list_dataset_versions(source_type)
    if not include_archived:
        versions = [v for v in versions if not v.get("archived")]
    return [_to_summary(v) for v in versions]


@router.get("/versions/{version_id}", response_model=DatasetVersionSummary)
def get_version(version_id: str) -> DatasetVersionSummary:
    version = db.get_dataset_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="dataset version not found")
    return _to_summary(version)
