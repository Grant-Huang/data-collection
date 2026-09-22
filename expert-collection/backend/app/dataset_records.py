"""Shared "records in this dataset_version, normalized to one shape regardless of
source_type" helper -- factored out of routers/datasets.py so routers/annotations.py (§9
Phase C-2, IMPLEMENTATION_PLAN.md section 9) can reuse the exact same normalization instead
of re-deriving it, now that annotation applies to both public_extracted and expert_collected
versions.
"""
from __future__ import annotations

from . import db


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
        })
    return out
