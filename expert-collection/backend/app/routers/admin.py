"""Admin endpoints -- PRD 16, honestly scoped (see IMPLEMENTATION_PLAN.md section 7): only
the audit log read endpoint lives here. Dataset publish/archive already live in
routers/datasets.py (that's where the action naturally belongs); this module doesn't
duplicate them. User/role management isn't implemented -- there's no real account system to
manage (assumption 1).
"""
from __future__ import annotations

from fastapi import APIRouter

from .. import audit

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/audit-log")
def get_audit_log(limit: int = 100) -> list[dict]:
    return audit.list_recent(limit)
