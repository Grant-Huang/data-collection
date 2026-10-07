"""Accumulated vocabulary and ontology entries (app/vocabulary.py) -- read-only views for the
数据分析员 (researcher) and 管理员 (admin) roles, plus the admin's one-off backfill from records
saved before accumulation existed. Like the rest of this app, role gating is front-end only
(no account system, IMPLEMENTATION_PLAN.md section 7); the backfill is audit-logged."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from .. import audit, vocabulary

router = APIRouter(prefix="/api/vocabulary", tags=["vocabulary"])


@router.get("/summary")
def get_summary() -> dict:
    return {"kinds": vocabulary.kinds(), "counts": vocabulary.summary()}


@router.get("/{layer}")
def list_entries(layer: str, kind: Optional[str] = None) -> list[dict]:
    if layer not in ("term", "ontology"):
        raise HTTPException(status_code=404, detail="layer 必须是 term 或 ontology")
    if kind and kind not in vocabulary.kinds()[layer]:
        raise HTTPException(status_code=400, detail=f"未知的类别：{kind}")
    return vocabulary.list_entries(layer, kind)


@router.post("/backfill")
def backfill(actor_role: str = "unknown") -> dict:
    result = vocabulary.backfill()
    audit.log(actor_role, "vocabulary_backfill", result)
    return result
