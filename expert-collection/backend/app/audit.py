"""Audit log -- PRD 16.3, honestly scoped (see IMPLEMENTATION_PLAN.md section 7): without a
real multi-user login system (assumption 1), "who" can only be the currently-selected role
from the frontend's role switcher, not a real account. Only records the one action that is
genuinely happening and meaningful today -- dataset publish/archive. Node/edge-level change
auditing would need a finer change-tracking store than what's persisted today, left for later.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from . import db


def log(actor_role: str, action: str, data: dict) -> None:
    db.append_audit_log({
        "id": uuid.uuid4().hex[:12],
        "actor_role": actor_role,
        "action": action,
        "detail": data,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


def list_recent(limit: int = 100) -> list[dict]:
    return db.list_audit_log(limit)
