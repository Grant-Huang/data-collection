"""SQLite persistence for WorkflowRecord (Phase 1 scope only, per IMPLEMENTATION_PLAN.md).

Not specified by the PRD -- the assumption we made is: one JSON blob per workflow row,
since the whole record (graph + turns + unresolved questions + completion) is always
read/written together and there's no cross-workflow query need yet. If Phase 3's
dataset/dashboard work needs to query into the graph structure, that's the point to
introduce real columns/tables -- not before.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "expert_workflows.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workflows (
            id TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dataset_versions (
            id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            version_number INTEGER NOT NULL,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL,
            archived INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            data TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS experiments (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id TEXT PRIMARY KEY,
            actor_role TEXT NOT NULL,
            action TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    # Prior annotation (IMPLEMENTATION_PLAN.md section 9.2): a chain, not independent
    # per-annotator rows -- each entry can point at the one it revises via
    # based_on_annotation_id, kept in `data`. Scoped to (version_id, record_id) rather than
    # written back into the immutable dataset_versions row, so annotating a public_extracted
    # record never mutates an already-published version.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prior_annotations (
            id TEXT PRIMARY KEY,
            version_id TEXT NOT NULL,
            record_id TEXT NOT NULL,
            data TEXT NOT NULL,
            annotated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_prior_annotations_lookup ON prior_annotations (version_id, record_id, annotated_at)"
    )
    # dataset_versions predates the `archived` column; add it for DBs created before this change.
    cols = [row[1] for row in conn.execute("PRAGMA table_info(dataset_versions)").fetchall()]
    if "archived" not in cols:
        conn.execute("ALTER TABLE dataset_versions ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
    return conn


def save(record: dict) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO workflows (id, data, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
            (record["id"], json.dumps(record, ensure_ascii=False), record["updated_at"]),
        )
        conn.commit()
    finally:
        conn.close()


def get(workflow_id: str) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute("SELECT data FROM workflows WHERE id = ?", (workflow_id,)).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def list_all() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute("SELECT data FROM workflows ORDER BY updated_at DESC").fetchall()
        return [json.loads(r[0]) for r in rows]
    finally:
        conn.close()


def save_dataset_version(version: dict) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO dataset_versions (id, source_type, version_number, data, created_at) VALUES (?, ?, ?, ?, ?)",
            (version["id"], version["source_type"], version["version_number"],
             json.dumps(version, ensure_ascii=False), version["created_at"]),
        )
        conn.commit()
    finally:
        conn.close()


def list_dataset_versions(source_type: Optional[str] = None) -> list[dict]:
    conn = _connect()
    try:
        if source_type:
            rows = conn.execute(
                "SELECT data FROM dataset_versions WHERE source_type = ? ORDER BY version_number DESC",
                (source_type,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT data FROM dataset_versions ORDER BY created_at DESC").fetchall()
        return [json.loads(r[0]) for r in rows]
    finally:
        conn.close()


def get_dataset_version(version_id: str) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute("SELECT data FROM dataset_versions WHERE id = ?", (version_id,)).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def archive_dataset_version(version_id: str) -> None:
    conn = _connect()
    try:
        row = conn.execute("SELECT data FROM dataset_versions WHERE id = ?", (version_id,)).fetchone()
        if not row:
            return
        version = json.loads(row[0])
        version["archived"] = True
        conn.execute(
            "UPDATE dataset_versions SET archived = 1, data = ? WHERE id = ?",
            (json.dumps(version, ensure_ascii=False), version_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_settings() -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute("SELECT data FROM settings WHERE id = 1").fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def save_settings(data: dict) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO settings (id, data) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET data = excluded.data",
            (json.dumps(data, ensure_ascii=False),),
        )
        conn.commit()
    finally:
        conn.close()


def save_experiment(exp: dict) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO experiments (id, status, data, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET status = excluded.status, data = excluded.data",
            (exp["id"], exp["status"], json.dumps(exp, ensure_ascii=False), exp["created_at"]),
        )
        conn.commit()
    finally:
        conn.close()


def get_experiment(exp_id: str) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute("SELECT data FROM experiments WHERE id = ?", (exp_id,)).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def list_experiments() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute("SELECT data FROM experiments ORDER BY created_at DESC").fetchall()
        return [json.loads(r[0]) for r in rows]
    finally:
        conn.close()


def append_audit_log(entry: dict) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO audit_log (id, actor_role, action, data, created_at) VALUES (?, ?, ?, ?, ?)",
            (entry["id"], entry["actor_role"], entry["action"], json.dumps(entry, ensure_ascii=False), entry["created_at"]),
        )
        conn.commit()
    finally:
        conn.close()


def list_audit_log(limit: int = 100) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute("SELECT data FROM audit_log ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(r[0]) for r in rows]
    finally:
        conn.close()


def save_annotation(entry: dict) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO prior_annotations (id, version_id, record_id, data, annotated_at) VALUES (?, ?, ?, ?, ?)",
            (entry["annotation_id"], entry["version_id"], entry["record_id"],
             json.dumps(entry, ensure_ascii=False), entry["annotated_at"]),
        )
        conn.commit()
    finally:
        conn.close()


def list_annotations(version_id: str, record_id: str) -> list[dict]:
    """Oldest first -- the order the chain was built in."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT data FROM prior_annotations WHERE version_id = ? AND record_id = ? ORDER BY annotated_at ASC",
            (version_id, record_id),
        ).fetchall()
        return [json.loads(r[0]) for r in rows]
    finally:
        conn.close()


def latest_annotation(version_id: str, record_id: str) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT data FROM prior_annotations WHERE version_id = ? AND record_id = ? ORDER BY annotated_at DESC LIMIT 1",
            (version_id, record_id),
        ).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def list_annotations_for_version(version_id: str) -> list[dict]:
    """One row per (version_id, record_id): the latest annotation only, for coverage stats."""
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT data FROM prior_annotations p1
            WHERE version_id = ? AND annotated_at = (
                SELECT MAX(annotated_at) FROM prior_annotations p2
                WHERE p2.version_id = p1.version_id AND p2.record_id = p1.record_id
            )
            """,
            (version_id,),
        ).fetchall()
        return [json.loads(r[0]) for r in rows]
    finally:
        conn.close()
