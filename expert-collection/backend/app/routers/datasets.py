"""Dataset publish + Dashboard read endpoints -- PRD 12.0 (publish = snapshot the draft pool
into an immutable dataset_version) and 13 (Dashboard reads a version's readiness scores).
Phase 3 sub-scope only covers source_type=expert_collected (see IMPLEMENTATION_PLAN.md
section 6) -- public_extracted has no import pipeline yet, so its version list is just empty.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response

from .. import anonymize, audit, db, explain, import_pipeline, quality, settings as settings_module
from ..models import DatasetVersionSummary, ImportConfirmRequest, PublishDatasetRequest

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


def _thresholds() -> tuple[float, float]:
    qp = settings_module.get_effective_settings()["quality_params"]
    return qp["near_dup_text_threshold"], qp["near_dup_structure_threshold"] or 0.7


@router.post("/import/precheck")
def import_precheck(payload: dict) -> dict:
    text_threshold, structure_threshold = _thresholds()
    try:
        return import_pipeline.precheck(payload, text_threshold, structure_threshold)
    except (KeyError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"上传内容不是预期的 {{dataset_meta, records[]}} 结构：{e}")


@router.post("/import/confirm", response_model=DatasetVersionSummary)
def import_confirm(req: ImportConfirmRequest) -> DatasetVersionSummary:
    text_threshold, structure_threshold = _thresholds()
    report = import_pipeline.precheck(req.payload, text_threshold, structure_threshold)
    if report["error_count"] > 0 and not req.import_records_without_errors:
        raise HTTPException(status_code=422, detail={"message": "预检有阻断错误，未确认跳过错误记录", "report": report})

    importable_ids = set(report["importable_record_ids"])
    records = [r for r in req.payload["records"] if r.get("record_id") in importable_ids]
    if not records:
        raise HTTPException(status_code=400, detail="没有可导入的记录")

    dataset_meta = req.payload["dataset_meta"]
    source_type = dataset_meta["source_type"]
    graphs = [r["graph"] for r in records]

    min_sample_size = settings_module.get_effective_settings()["quality_params"]["min_sample_size"]
    readiness = quality.compute_readiness(graphs, min_sample_size=min_sample_size)
    named_records = [{"id": r.get("record_id"), "name": r.get("scenario", {}).get("scenario_name") or r.get("record_id")} for r in records]
    explanations = explain.explain_all(readiness, named_records)

    existing = db.list_dataset_versions(source_type)
    version_number = (max((v["version_number"] for v in existing), default=0)) + 1

    version = {
        "id": uuid.uuid4().hex[:12],
        "source_type": source_type,
        "name": req.name or dataset_meta.get("name") or source_type,
        "version_number": version_number,
        "workflow_ids": [r.get("record_id") for r in records],
        "workflow_count": len(records),
        "total_steps": sum(len(g["nodes"]) for g in graphs),
        "readiness": readiness,
        "explanations": explanations,
        "created_at": _now(),
        "archived": False,
        "records": records,  # public_extracted has no separate `workflows` table row per record
    }
    db.save_dataset_version(version)

    audit.log(req.actor_role or "unknown", "dataset_import", {
        "dataset_version_id": version["id"], "source_type": source_type,
        "version_number": version_number, "record_count": len(records),
        "skipped_error_records": report["total_records"] - len(records),
    })

    return _to_summary(version)


def _records_for_export(version: dict) -> list[dict]:
    if version["source_type"] == "public_extracted":
        return version.get("records", [])
    # expert_collected: reconstruct a record-shaped dict from each stored WorkflowRecord.
    out = []
    for wid in version["workflow_ids"]:
        w = db.get(wid)
        if not w:
            continue
        out.append({
            "record_id": w["id"],
            "scenario": {"scenario_name": w["name"]},
            "graph": w["graph"],
            "provenance": {"source_type": "expert_collected"},
        })
    return out


@router.get("/versions/{version_id}/export")
def export_version(version_id: str, format: str = "raw") -> Response:
    version = db.get_dataset_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="dataset version not found")
    if format not in ("raw", "anonymized", "role_normalized"):
        raise HTTPException(status_code=400, detail="format 必须是 raw / anonymized / role_normalized 之一")

    records = _records_for_export(version)
    if format == "role_normalized":
        records = [{**r, "graph": anonymize.apply_role_normalization(r["graph"])} for r in records]
    elif format == "anonymized":
        records = [anonymize.apply_anonymization({**r, "graph": anonymize.apply_role_normalization(r["graph"])}) for r in records]

    export_payload = {
        "dataset_meta": {
            "dataset_id": version["id"], "name": version["name"],
            "source_type": version["source_type"],  # PRD 12.3: must be preserved on export
            "schema_version": "2.0", "created_at": version["created_at"],
        },
        "records": records,
        "export_format": format,
    }
    body = json.dumps(export_payload, ensure_ascii=False, indent=2)
    return Response(
        content=body, media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{version["id"]}_{format}.json"'},
    )


@router.get("/versions/{version_id}/drill-down")
def drill_down(version_id: str, dimension: str) -> dict:
    """PRD 13.4: locate the specific records dragging a dimension's score down."""
    version = db.get_dataset_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="dataset version not found")
    dim = version["readiness"]["dimensions"].get(dimension)
    if not dim:
        raise HTTPException(status_code=404, detail="未知的评分维度")

    records = _records_for_export(version)
    problems: list[dict] = []
    for r in records:
        graph = r["graph"]
        name = r.get("scenario", {}).get("scenario_name") or r.get("record_id")
        flagged, reason = _flag_for_dimension(dimension, graph)
        if flagged:
            problems.append({"record_id": r.get("record_id"), "name": name, "reason": reason})

    return {"dimension": dimension, "score": dim["score"], "problem_records": problems[:50]}


def _flag_for_dimension(dimension: str, graph: dict) -> tuple[bool, str]:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    if dimension == "graph_completeness":
        connected = {e["from"] for e in edges} | {e["to"] for e in edges}
        isolated = [n for n in nodes if n["node_id"] not in connected]
        if isolated:
            return True, f"含孤立节点：{', '.join(n['label'] for n in isolated)}"
        for n in nodes:
            if n["node_type"] == "decision":
                out = [e for e in edges if e["from"] == n["node_id"] and e["edge_type"] == "conditional"]
                if len(out) < 2:
                    return True, f"判断节点「{n['label']}」条件分支不足两条"
        return False, ""
    if dimension == "completeness":
        if len(nodes) < 5:
            return True, f"步骤数偏少（{len(nodes)} 个）"
        return False, ""
    if dimension == "structural_diversity":
        types = {n["node_type"] for n in nodes}
        if not ({"decision", "parallel_split"} & types):
            return True, "线性流程，无分支或并行结构"
        return False, ""
    if dimension == "extractability":
        low_conf = [n for n in nodes if n.get("confidence", 1.0) < 0.7]
        if low_conf:
            return True, f"{len(low_conf)} 个节点抽取置信度偏低"
        return False, ""
    return False, ""


@router.get("/trend")
def get_trend(source_type: str = "expert_collected") -> dict:
    """PRD 13.5: readiness score trend across published versions."""
    versions = [v for v in db.list_dataset_versions(source_type) if not v.get("archived")]
    versions.sort(key=lambda v: v["version_number"])
    points = [
        {
            "version_number": v["version_number"], "created_at": v["created_at"],
            "overall": v["readiness"]["overall"],
            "dimensions": {k: d["score"] for k, d in v["readiness"]["dimensions"].items()},
        }
        for v in versions
    ]
    return {"source_type": source_type, "points": points}
