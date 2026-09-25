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
    # Rework revisions (IMPLEMENTATION_PLAN.md section 16): each row is one corrected graph
    # produced after a round of annotation settled on "needs_revision". Like prior_annotations,
    # scoped to (version_id, record_id) so the published dataset_versions row stays immutable --
    # a record's current graph is its latest revision's graph, or the original if none.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS record_revisions (
            id TEXT PRIMARY KEY,
            version_id TEXT NOT NULL,
            record_id TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_record_revisions_lookup ON record_revisions (version_id, record_id, created_at)"
    )
    # Section 17 annotation review sessions: one annotator's conversation + working graph on
    # one record. Kept out of prior_annotations (which only gets the final verdict) so an
    # unfinished conversation never counts as an annotation.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS annotation_sessions (
            id TEXT PRIMARY KEY,
            version_id TEXT NOT NULL,
            record_id TEXT NOT NULL,
            data TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_annotation_sessions_lookup ON annotation_sessions (version_id, record_id)"
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


def rename_dataset_version(version_id: str, name: str) -> None:
    conn = _connect()
    try:
        row = conn.execute("SELECT data FROM dataset_versions WHERE id = ?", (version_id,)).fetchone()
        if not row:
            return
        version = json.loads(row[0])
        version["name"] = name
        conn.execute(
            "UPDATE dataset_versions SET data = ? WHERE id = ?",
            (json.dumps(version, ensure_ascii=False), version_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_dataset_version(version_id: str) -> None:
    conn = _connect()
    try:
        conn.execute("DELETE FROM dataset_versions WHERE id = ?", (version_id,))
        conn.execute("DELETE FROM prior_annotations WHERE version_id = ?", (version_id,))
        conn.commit()
    finally:
        conn.close()


def set_dataset_version_gold(version_id: str, is_gold: bool) -> None:
    """IMPLEMENTATION_PLAN.md section 14, §9 Phase C-1: PRD 16.1's "标记为 Gold 版本" --
    stored only in the `data` JSON blob (no new SQL column) since nothing needs to filter on
    it at the SQL level yet, same as most other per-version flags.
    """
    conn = _connect()
    try:
        row = conn.execute("SELECT data FROM dataset_versions WHERE id = ?", (version_id,)).fetchone()
        if not row:
            return
        version = json.loads(row[0])
        version["is_gold"] = is_gold
        conn.execute(
            "UPDATE dataset_versions SET data = ? WHERE id = ?",
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


def list_annotations_by_record(version_id: str) -> dict[str, list[dict]]:
    """Every annotation in a version, grouped by record_id (each list oldest first) -- one
    query instead of one per record for the annotation list / readiness computation.
    """
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT record_id, data FROM prior_annotations WHERE version_id = ? ORDER BY annotated_at ASC",
            (version_id,),
        ).fetchall()
    finally:
        conn.close()
    out: dict[str, list[dict]] = {}
    for record_id, data in rows:
        out.setdefault(record_id, []).append(json.loads(data))
    return out


def save_revision(entry: dict) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO record_revisions (id, version_id, record_id, data, created_at) VALUES (?, ?, ?, ?, ?)",
            (entry["revision_id"], entry["version_id"], entry["record_id"],
             json.dumps(entry, ensure_ascii=False), entry["created_at"]),
        )
        conn.commit()
    finally:
        conn.close()


def list_revisions(version_id: str, record_id: str) -> list[dict]:
    """Oldest first."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT data FROM record_revisions WHERE version_id = ? AND record_id = ? ORDER BY created_at ASC",
            (version_id, record_id),
        ).fetchall()
        return [json.loads(r[0]) for r in rows]
    finally:
        conn.close()


def list_revisions_by_record(version_id: str) -> dict[str, list[dict]]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT record_id, data FROM record_revisions WHERE version_id = ? ORDER BY created_at ASC",
            (version_id,),
        ).fetchall()
    finally:
        conn.close()
    out: dict[str, list[dict]] = {}
    for record_id, data in rows:
        out.setdefault(record_id, []).append(json.loads(data))
    return out


def save_review_session(session: dict) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO annotation_sessions (id, version_id, record_id, data, updated_at) VALUES (?, ?, ?, ?, ?)",
            (session["session_id"], session["version_id"], session["record_id"],
             json.dumps(session, ensure_ascii=False), session["updated_at"]),
        )
        conn.commit()
    finally:
        conn.close()


def get_review_session(session_id: str) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute("SELECT data FROM annotation_sessions WHERE id = ?", (session_id,)).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def list_review_sessions(version_id: str, record_id: str) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT data FROM annotation_sessions WHERE version_id = ? AND record_id = ? ORDER BY updated_at ASC",
            (version_id, record_id),
        ).fetchall()
        return [json.loads(r[0]) for r in rows]
    finally:
        conn.close()
