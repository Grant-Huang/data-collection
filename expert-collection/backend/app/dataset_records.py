"""Shared "records in this dataset_version, normalized to one shape regardless of
source_type" helper -- factored out of routers/datasets.py so routers/annotations.py (§9
Phase C-2, IMPLEMENTATION_PLAN.md section 9) can reuse the exact same normalization instead
of re-deriving it, now that annotation applies to both public_extracted and expert_collected
versions.
"""
from __future__ import annotations

from . import db


def published_workflow_ids() -> set[str]:
    """Every workflow id referenced by any dataset_version, archived versions included --
    an archived version is still a published snapshot someone may have exported or run an
    experiment on, so its records count as "已录入数据集" too.
    """
    ids: set[str] = set()
    for version in db.list_dataset_versions():
        ids.update(version.get("workflow_ids", []))
    return ids


def versions_containing(workflow_id: str) -> list[dict]:
    """The dataset_versions that reference `workflow_id`, newest first. Used to block
    graph regeneration: expert_collected versions don't snapshot the graph, they read it
    back live through `records_for_export` below, so rewriting a published workflow's graph
    would silently change an already-published (supposedly immutable) version.
    """
    return [
        {
            "id": v["id"],
            "source_type": v["source_type"],
            "version_number": v["version_number"],
            "archived": bool(v.get("archived", False)),
        }
        for v in db.list_dataset_versions()
        if workflow_id in v.get("workflow_ids", [])
    ]


def records_for_export(version: dict) -> list[dict]:
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
            "case_context": w.get("case_context"),
            "manufacturing_context": w.get("manufacturing_context"),
            # Dual-DAG upper layer (IMPLEMENTATION_PLAN.md section 18); `graph` above is the
            # step / SOP layer. None for sessions collected before the task layer existed.
            "task_workflow": w.get("task_workflow"),
        })
    return out


# §14.4 Dataset Slice -- these are exactly the free-text/enum fields
# `manufacturing_context` carries (models.py::ManufacturingContext, mirroring
# schema/workflow_graph_schema_v2.json), not an invented list.
SLICEABLE_FIELDS = ("manufacturing_mode", "industry", "site_type", "process_area", "product_family")

UNCLASSIFIED_LABEL = "未填写"


def slice_counts(version: dict, field: str) -> list[dict]:
    """Group this version's records by one `manufacturing_context` field and count them --
    real counts over real published records, not a placeholder for a feature with nowhere to
    plug in: both source types reach this through the same `records_for_export` shape.
    """
    if field not in SLICEABLE_FIELDS:
        raise ValueError(f"unsupported slice field: {field}")
    records = records_for_export(version)
    counts: dict[str, int] = {}
    for r in records:
        mc = r.get("manufacturing_context") or {}
        value = mc.get(field) or UNCLASSIFIED_LABEL
        counts[value] = counts.get(value, 0) + 1
    total = len(records)
    return [
        {"value": value, "count": count, "pct": round(count / total, 3) if total else 0.0}
        for value, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
