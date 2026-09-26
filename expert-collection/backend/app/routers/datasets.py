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

from .. import annotation_signals, anonymize, audit, db, dataset_records, explain, gold_annotation, import_pipeline, quality, settings as settings_module
from ..models import (
    DatasetVersionListResponse,
    DatasetVersionSummary,
    DuplicateCheckRequest,
    DuplicateCheckResult,
    DuplicateMatch,
    ImportConfirmRequest,
    PublishDatasetRequest,
    RenameDatasetVersionRequest,
)

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
    # Archived sessions are the expert/admin saying "set this one aside" -- keep them out of
    # the next publish until they're unarchived.
    return [
        w for w in db.list_all()
        if w["status"] == "expert_confirmed" and w["id"] not in already_published
        and not w.get("archived", False)
    ]


def _live_annotation_readiness(version: dict) -> dict:
    """§9 Phase C-2: annotation_readiness is the one dimension recomputed at read time
    instead of frozen at publish -- see quality.compute_annotation_readiness's docstring.
    """
    records = dataset_records.records_for_export(version)
    annotations = db.list_annotations_by_record(version["id"])
    revisions = db.list_revisions_by_record(version["id"])
    gold_count = double_count = arbitrated_count = 0
    kappa_pairs: list[tuple[str, str]] = []
    for r in records:
        history = annotations.get(r["record_id"], [])
        if gold_annotation.compute_gold_status(history, revisions.get(r["record_id"], [])) == "gold":
            gold_count += 1
        # Rounds (IMPLEMENTATION_PLAN.md section 16): a record counts as double-annotated
        # once any of its rounds has two independent annotations; every such round
        # contributes one pair to kappa.
        pairs = gold_annotation.kappa_pairs(history)
        if pairs:
            double_count += 1
            kappa_pairs.extend(pairs)
        if any(a.get("role_in_process") == "arbitration" for a in history):
            arbitrated_count += 1

    min_sample_size = settings_module.get_effective_settings()["quality_params"]["min_sample_size"]
    return quality.compute_annotation_readiness(
        total_records=len(records), gold_count=gold_count, double_annotated_count=double_count,
        arbitrated_count=arbitrated_count, agreement_kappa=gold_annotation.cohens_kappa(kappa_pairs),
        min_sample_size=min_sample_size,
    )


def _to_summary(version: dict) -> DatasetVersionSummary:
    readiness = version["readiness"]
    dims = dict(readiness["dimensions"])
    if version["source_type"] in ("public_extracted", "expert_collected"):
        dims["annotation_readiness"] = _live_annotation_readiness(version)
    scores = [dims[key]["score"] for key in quality.DIMENSION_WEIGHTS]
    if all(s is not None for s in scores):
        overall = round(sum(dims[key]["score"] * w for key, w in quality.DIMENSION_WEIGHTS.items()), 1)
        band = quality.band(overall)
    else:
        overall, band = readiness["overall"], readiness["band"]
    readiness = {**readiness, "overall": overall, "band": band, "dimensions": dims}

    dims_with_explanations = {
        key: {**dim, "explanation": version["explanations"].get(key, "")}
        for key, dim in readiness["dimensions"].items()
    }
    return DatasetVersionSummary(
        id=version["id"],
        source_type=version["source_type"],
        name=version.get("name") or version["source_type"],
        version_number=version["version_number"],
        workflow_count=version["workflow_count"],
        total_steps=version["total_steps"],
        microflow_count=None,  # PRD 13.2: needs subgraph mining, not implemented this phase
        created_at=version["created_at"],
        readiness={**readiness, "dimensions": dims_with_explanations},
        archived=version.get("archived", False),
        is_gold=version.get("is_gold", False),
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
    case_contexts = [w.get("case_context") for w in pool]
    min_sample_size = settings_module.get_effective_settings()["quality_params"]["min_sample_size"]
    readiness = quality.compute_readiness(graphs, min_sample_size=min_sample_size, case_contexts=case_contexts)
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


@router.post("/versions/{version_id}/rename", response_model=DatasetVersionSummary)
def rename_version(version_id: str, req: RenameDatasetVersionRequest) -> DatasetVersionSummary:
    version = db.get_dataset_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="dataset version not found")
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="名称不能为空")
    db.rename_dataset_version(version_id, name)
    version["name"] = name

    audit.log(req.actor_role or "unknown", "dataset_rename", {"dataset_version_id": version_id, "name": name})

    return _to_summary(version)


@router.delete("/versions/{version_id}")
def delete_version(version_id: str, actor_role: str = "unknown") -> dict:
    """Hard delete -- unlike archive (reversible-in-spirit, just hidden from the default
    list), this permanently removes the version row and its prior annotations. Scoped to
    public_extracted in the frontend (each import is its own standalone dataset there,
    unlike expert_collected's single continuously-published version), but not enforced here
    since there's no real permission system yet (same honest gap as every other admin
    action in this codebase).
    """
    version = db.get_dataset_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="dataset version not found")
    db.delete_dataset_version(version_id)

    audit.log(actor_role, "dataset_delete", {
        "dataset_version_id": version_id, "source_type": version["source_type"],
        "version_number": version["version_number"], "name": version.get("name"),
    })

    return {"ok": True}


@router.post("/versions/{version_id}/mark-gold", response_model=DatasetVersionSummary)
def mark_gold_version(version_id: str, is_gold: bool = True, actor_role: str = "unknown") -> DatasetVersionSummary:
    """PRD 16.1/16.2: admin-only in principle (no backend permission enforcement yet -- same
    honest gap as every other admin action in this codebase, see assumption 1/5/7; the
    frontend hides this control for non-admin roles, the audit log records who actually did it).
    """
    version = db.get_dataset_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="dataset version not found")
    db.set_dataset_version_gold(version_id, is_gold)
    version["is_gold"] = is_gold

    audit.log(actor_role, "dataset_mark_gold" if is_gold else "dataset_unmark_gold",
              {"dataset_version_id": version_id})

    return _to_summary(version)


@router.get("/versions", response_model=list[DatasetVersionSummary])
def list_versions(source_type: str = "expert_collected", include_archived: bool = False) -> list[DatasetVersionSummary]:
    versions = db.list_dataset_versions(source_type)
    if not include_archived:
        versions = [v for v in versions if not v.get("archived")]
    return [_to_summary(v) for v in versions]


def _version_matches_query(version: dict, query: str) -> bool:
    """Substring match against name and version number -- "v3"/"3" both hit version_number 3,
    so searching either the way a version is labeled in the UI ("v3") or the bare number works.
    """
    name = (version.get("name") or "").lower()
    number = version["version_number"]
    return query in name or query in f"v{number}" or query == str(number)


@router.get("/versions/search", response_model=DatasetVersionListResponse)
def search_versions(
    source_type: str = "expert_collected",
    query: str = "",
    page: int = 1,
    page_size: int = 20,
    include_archived: bool = False,
) -> DatasetVersionListResponse:
    """Dashboard「全部」入口：进入某个来源（专家集/公有集）的 Dashboard 后默认只看最新版本，
    点「查看全部」才翻到这个分页 + 可查询的完整版本列表，而不是把所有版本一次性堆在 Dashboard
    首屏里。`query` 匹配版本名称或版本号（"v3" 或 "3" 都能命中第 3 版）。
    """
    versions = db.list_dataset_versions(source_type)
    if not include_archived:
        versions = [v for v in versions if not v.get("archived")]
    q = query.strip().lower()
    if q:
        versions = [v for v in versions if _version_matches_query(v, q)]

    total = len(versions)
    page = max(page, 1)
    page_size = max(1, min(page_size, 100))
    start = (page - 1) * page_size
    page_items = versions[start:start + page_size]
    return DatasetVersionListResponse(
        items=[_to_summary(v) for v in page_items], total=total, page=page, page_size=page_size,
    )


@router.get("/versions/{version_id}", response_model=DatasetVersionSummary)
def get_version(version_id: str) -> DatasetVersionSummary:
    version = db.get_dataset_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="dataset version not found")
    return _to_summary(version)


def _thresholds() -> tuple[float, float]:
    qp = settings_module.get_effective_settings()["quality_params"]
    return qp["near_dup_text_threshold"], qp["near_dup_structure_threshold"] or 0.7


def _existing_records_for_gatekeeping(source_type: str) -> list[dict]:
    """Every record already published under `source_type`, across all still-active (not
    archived) dataset_versions -- the cross-version comparison corpus for import_pipeline's
    strict gatekeeping (IMPLEMENTATION_PLAN.md section 10). Archived versions are excluded:
    they were intentionally retired, so gatekeeping against still-active data only.
    Reuses _records_for_export so expert_collected and public_extracted are normalized the
    same way this module already normalizes them for every other cross-cutting use (export,
    drill-down).
    """
    out: list[dict] = []
    for v in db.list_dataset_versions(source_type):
        if v.get("archived"):
            continue
        for r in _records_for_export(v):
            out.append({**r, "_version_number": v["version_number"]})
    return out


@router.post("/duplicate-check", response_model=DuplicateCheckResult)
def duplicate_check(req: DuplicateCheckRequest) -> DuplicateCheckResult:
    """Standalone查重接口 (IMPLEMENTATION_PLAN.md section 10): classifies every record in
    `payload` against the full existing corpus of the same source_type, independent of
    precheck/import -- for inspecting a file's relationship to already-published data
    (e.g. before deciding whether to fix and re-upload it) without going through the whole
    ten-step precheck. Uses the exact same classification import/confirm relies on
    internally, so results here are consistent with what a subsequent import would block.
    """
    source_type = (req.payload.get("dataset_meta") or {}).get("source_type")
    records = req.payload.get("records")
    if not source_type or records is None:
        raise HTTPException(status_code=400, detail="上传内容需要包含 dataset_meta.source_type 和 records[]")

    text_threshold, structure_threshold = _thresholds()
    existing = _existing_records_for_gatekeeping(source_type)
    matches = import_pipeline.compare_cross_version(records, existing, text_threshold, structure_threshold)

    duplicates = [DuplicateMatch(**m) for m in matches if m["kind"] == "duplicate"]
    reuse_candidates = [DuplicateMatch(**m) for m in matches if m["kind"] == "microflow_reuse_candidate"]
    other = [DuplicateMatch(**m) for m in matches if m["kind"] == "content_match_structure_diff"]

    return DuplicateCheckResult(
        source_type=source_type, total_records=len(records),
        duplicates=duplicates, reuse_candidates=reuse_candidates, other_matches=other,
    )


@router.post("/import/precheck")
def import_precheck(payload: dict) -> dict:
    text_threshold, structure_threshold = _thresholds()
    source_type = (payload.get("dataset_meta") or {}).get("source_type")
    existing = _existing_records_for_gatekeeping(source_type) if source_type else []
    try:
        return import_pipeline.precheck(payload, text_threshold, structure_threshold, existing_records=existing)
    except (KeyError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"上传内容不是预期的 {{dataset_meta, records[]}} 结构：{e}")


@router.post("/import/confirm", response_model=DatasetVersionSummary)
def import_confirm(req: ImportConfirmRequest) -> DatasetVersionSummary:
    text_threshold, structure_threshold = _thresholds()
    source_type = (req.payload.get("dataset_meta") or {}).get("source_type")
    existing = _existing_records_for_gatekeeping(source_type) if source_type else []
    report = import_pipeline.precheck(req.payload, text_threshold, structure_threshold, existing_records=existing)
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
        # Cross-version precheck matches, kept so the annotation panel can show them later
        # (annotation_signals.py) -- within-batch matches and graph issues are recomputed live.
        "precheck_issues": {
            rid: [
                {"code": i["code"], "message": i["message"]} for i in report["issues"]
                if i.get("record_id") == rid and i["code"].startswith(annotation_signals.STORED_CODE_PREFIXES)
            ]
            for rid in importable_ids
        },
    }
    db.save_dataset_version(version)

    audit.log(req.actor_role or "unknown", "dataset_import", {
        "dataset_version_id": version["id"], "source_type": source_type,
        "version_number": version_number, "record_count": len(records),
        "skipped_error_records": report["total_records"] - len(records),
    })

    return _to_summary(version)


_records_for_export = dataset_records.records_for_export


def _with_gold(version: dict, records: list[dict]) -> list[dict]:
    """Export carries both graphs (IMPLEMENTATION_PLAN.md section 17.8, user decision "两个都要"):
    - `graph`: the record as collected / imported -- unchanged, so an export still re-imports;
    - `gold_graph`: the graph the Gold process settled on -- the corrected graph when the
      annotators (or the arbitrator) adopted a correction, the record's current graph when it
      was accepted as is, null while the record isn't Gold (in progress, or discarded).
    `annotation` (already an object in schema v2's workflow_record) gets the Gold outcome;
    keys an imported record already had there are kept. Verdicts and reasons only appear
    once a record is settled, same blind-review rule as the annotation list."""
    annotations = db.list_annotations_by_record(version["id"])
    revisions = db.list_revisions_by_record(version["id"])
    out = []
    for r in records:
        rid = r.get("record_id")
        history = annotations.get(rid, [])
        revs = revisions.get(rid, [])
        state = gold_annotation.compute_state(history, revs)
        current = revs[-1]["graph"] if revs else r["graph"]
        done = state["stage"] == "done"
        gold = state["gold_status"] == "gold"
        annotation = {
            **(r.get("annotation") or {}),
            "gold_status": state["gold_status"],
            "final_verdict": state["outcome"] if done else None,
            "corrected": bool(state["final_graph"]),
            "reason_tags": sorted({t for a in state["round_annotations"] for t in (a.get("reason_tags") or [])}) if done else [],
            "annotator_count": len({a["annotator_name"].strip().lower() for a in history}),
            "adjudicated": any(a.get("role_in_process") == "arbitration" for a in state["round_annotations"]) and done,
        }
        out.append({**r, "gold_graph": (state["final_graph"] or current) if gold else None, "annotation": annotation})
    return out


@router.get("/versions/{version_id}/export")
def export_version(version_id: str, format: str = "raw") -> Response:
    version = db.get_dataset_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="dataset version not found")
    if format not in ("raw", "anonymized", "role_normalized"):
        raise HTTPException(status_code=400, detail="format 必须是 raw / anonymized / role_normalized 之一")

    records = _with_gold(version, _records_for_export(version))
    if format == "role_normalized":
        records = [{**r, "graph": anonymize.apply_role_normalization(r["graph"]),
                    "gold_graph": anonymize.apply_role_normalization(r["gold_graph"]) if r["gold_graph"] else None}
                   for r in records]
    elif format == "anonymized":
        records = [
            {**anonymize.apply_anonymization({**r, "graph": anonymize.apply_role_normalization(r["graph"])}),
             "gold_graph": anonymize.apply_anonymization({"graph": anonymize.apply_role_normalization(r["gold_graph"])})["graph"]
             if r["gold_graph"] else None}
            for r in records
        ]

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


@router.get("/versions/{version_id}/slice")
def slice_by_field(version_id: str, field: str) -> dict:
    """§14.4 Dataset Slice -- real per-value counts from this version's own
    `manufacturing_context` data (see dataset_records.SLICEABLE_FIELDS), not a placeholder
    with nowhere to plug in: both source types already carry this object (public_extracted's
    import schema requires it; expert_collected sets it via the manufacturing-context PUT
    endpoint), it just wasn't sliced by anything before this.
    """
    version = db.get_dataset_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="dataset version not found")
    if field not in dataset_records.SLICEABLE_FIELDS:
        raise HTTPException(status_code=400, detail=f"不支持的切片字段：{field}")
    return {"field": field, "buckets": dataset_records.slice_counts(version, field)}


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
