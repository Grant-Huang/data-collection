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


# DB files whose schema is already in place in this process (C5). Every function here opens its
# own short-lived connection (FastAPI runs sync endpoints on a thread pool, and a connection
# can't be shared across threads by default); re-running a dozen CREATE TABLE / PRAGMA
# statements on each of them cost more than the queries themselves when a dataset endpoint
# reads a few hundred records. Keyed by path because tests point DB_PATH at a fresh file each.
_schema_ready: set[str] = set()


def _connect() -> sqlite3.Connection:
    path = str(DB_PATH)
    if path in _schema_ready:
        return sqlite3.connect(DB_PATH)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    _create_schema(conn)
    conn.commit()
    _schema_ready.add(path)
    return conn


def _create_schema(conn: sqlite3.Connection) -> None:
    # WAL: readers (the Dashboard, the session list) no longer wait for a writer (a turn being
    # saved) and vice versa. Persistent -- stored in the DB file itself.
    conn.execute("PRAGMA journal_mode=WAL")
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    # Accumulated vocabulary terms and ontology entries (app/vocabulary.py): append-only, one
    # row per (layer, kind, key); never rewritten from or back into the records they came from.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS accumulated_entries (
            layer TEXT NOT NULL,
            kind TEXT NOT NULL,
            key TEXT NOT NULL,
            data TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            PRIMARY KEY (layer, kind, key)
        )
        """
    )
    # dataset_versions predates the `archived` column; add it for DBs created before this change.
    cols = [row[1] for row in conn.execute("PRAGMA table_info(dataset_versions)").fetchall()]
    if "archived" not in cols:
        conn.execute("ALTER TABLE dataset_versions ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
    # Opening a session asks "is this workflow in any published dataset?" (it decides whether
    # the graph may still be regenerated / edited). Answering that from `data` parsed every
    # version in full -- an imported public dataset carries all of its records inline, so a few
    # imports made each session switch take most of a second. `workflow_ids` keeps just the id
    # list (JSON array) beside the blob; ids never change after a version is saved. Rows saved
    # before the column existed are filled once here, by SQLite itself.
    if "workflow_ids" not in cols:
        conn.execute("ALTER TABLE dataset_versions ADD COLUMN workflow_ids TEXT")
    conn.execute("UPDATE dataset_versions SET workflow_ids = coalesce(data -> '$.workflow_ids', '[]') WHERE workflow_ids IS NULL")
    # C4: the session list only needs a handful of fields, but each record also carries the
    # whole transcript and up to 30 graph snapshots (review_agent's undo history) -- a few
    # hundred KB per session. Parsing every full record just to list them took ~4.5s at 500
    # sessions, on every turn (the list is refreshed after each message). `summary` keeps the
    # list fields as a small JSON next to the blob; NULL for rows saved before this column
    # existed, which list_summaries() fills in on first read.
    cols = [row[1] for row in conn.execute("PRAGMA table_info(workflows)").fetchall()]
    if "summary" not in cols:
        conn.execute("ALTER TABLE workflows ADD COLUMN summary TEXT")


# Fields of a workflow record the session list needs (routers/expert_workflows.list_workflows).
_SUMMARY_FIELDS = ("id", "name", "status", "updated_at", "pinned", "archived", "deleted")


def _summary(record: dict) -> str:
    summary = {k: record.get(k) for k in _SUMMARY_FIELDS}
    summary["completion_score"] = (record.get("completion") or {}).get("score", 0.0)
    return json.dumps(summary, ensure_ascii=False)


def save(record: dict) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO workflows (id, data, updated_at, summary) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at, "
            "summary = excluded.summary",
            (record["id"], json.dumps(record, ensure_ascii=False), record["updated_at"], _summary(record)),
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


def list_summaries() -> list[dict]:
    """Session-list fields for every workflow, newest first, without parsing the full records
    (see `_summary`). Rows saved before the `summary` column existed are summarized from their
    full record once and written back, so later reads stay cheap."""
    conn = _connect()
    try:
        rows = conn.execute("SELECT id, summary FROM workflows ORDER BY updated_at DESC").fetchall()
        out: list[dict] = []
        for workflow_id, summary in rows:
            if summary is None:
                data = conn.execute("SELECT data FROM workflows WHERE id = ?", (workflow_id,)).fetchone()[0]
                summary = _summary(json.loads(data))
                conn.execute("UPDATE workflows SET summary = ? WHERE id = ?", (summary, workflow_id))
            out.append(json.loads(summary))
        conn.commit()
        return out
    finally:
        conn.close()


_IN_CHUNK = 500  # stay well under SQLite's bound-parameter limit


def get_fields(workflow_ids: list[str], fields: tuple[str, ...]) -> dict[str, dict]:
    """Only the given top-level fields of each workflow, keyed by id (missing ids left out).
    Dataset code reads a record's graph and contexts; the rest of the blob -- the transcript and
    up to 30 undo snapshots, most of its size -- was parsed in Python just to be thrown away,
    which made publishing / the Dashboard take seconds at a few hundred records (C5). SQLite's
    `->` operator cuts the fields out in C and hands back only their JSON text."""
    if not workflow_ids:
        return {}
    # Field names go into the SQL text, so only plain identifiers are accepted (they are
    # constants at every call site anyway).
    assert all(f.isidentifier() for f in fields), fields
    cols = ", ".join(f"data -> '$.{f}'" for f in fields)
    out: dict[str, dict] = {}
    conn = _connect()
    try:
        for i in range(0, len(workflow_ids), _IN_CHUNK):
            chunk = workflow_ids[i:i + _IN_CHUNK]
            marks = ",".join("?" * len(chunk))
            for row in conn.execute(f"SELECT id, {cols} FROM workflows WHERE id IN ({marks})", chunk):
                out[row[0]] = {f: (json.loads(v) if v is not None else None) for f, v in zip(fields, row[1:])}
        return out
    finally:
        conn.close()


def existing_ids(workflow_ids: list[str]) -> list[str]:
    """`workflow_ids` minus the ones with no row, order kept -- without reading any record."""
    if not workflow_ids:
        return []
    found: set[str] = set()
    conn = _connect()
    try:
        for i in range(0, len(workflow_ids), _IN_CHUNK):
            chunk = workflow_ids[i:i + _IN_CHUNK]
            marks = ",".join("?" * len(chunk))
            found.update(r[0] for r in conn.execute(f"SELECT id FROM workflows WHERE id IN ({marks})", chunk))
    finally:
        conn.close()
    return [w for w in workflow_ids if w in found]


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
            "INSERT INTO dataset_versions (id, source_type, version_number, data, created_at, workflow_ids) VALUES (?, ?, ?, ?, ?, ?)",
            (version["id"], version["source_type"], version["version_number"],
             json.dumps(version, ensure_ascii=False), version["created_at"],
             json.dumps(version.get("workflow_ids") or [], ensure_ascii=False)),
        )
        conn.commit()
    finally:
        conn.close()


def versions_referencing(workflow_id: str) -> list[dict]:
    """id / source_type / version_number / archived of every version that lists `workflow_id`,
    newest first -- read from the `workflow_ids` column only, never the version blobs."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, source_type, version_number, archived FROM dataset_versions "
            "WHERE EXISTS (SELECT 1 FROM json_each(dataset_versions.workflow_ids) WHERE value = ?) "
            "ORDER BY created_at DESC",
            (workflow_id,),
        ).fetchall()
        return [{"id": i, "source_type": t, "version_number": n, "archived": bool(a)} for i, t, n, a in rows]
    finally:
        conn.close()


def referenced_workflow_ids() -> set[str]:
    """Every workflow id any version lists (archived versions included), same column."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT DISTINCT j.value FROM dataset_versions, json_each(dataset_versions.workflow_ids) AS j"
        ).fetchall()
        return {r[0] for r in rows if isinstance(r[0], str)}
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


def get_cache(key: str) -> Optional[str]:
    """Get a value from cache."""
    conn = _connect()
    try:
        row = conn.execute("SELECT value FROM cache WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def set_cache(key: str, value: str) -> None:
    """Set a value in cache."""
    from datetime import datetime
    conn = _connect()
    try:
        now = datetime.utcnow().isoformat() + "Z"
        conn.execute(
            "INSERT INTO cache (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, value, now),
        )
        conn.commit()
    finally:
        conn.close()


def get_accumulated(layer: str, kind: str, key: str) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute("SELECT data FROM accumulated_entries WHERE layer = ? AND kind = ? AND key = ?",
                           (layer, kind, key)).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def upsert_accumulated(entry: dict) -> None:
    """Insert or replace one accumulated entry; first_seen_at is kept from the first insert."""
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO accumulated_entries (layer, kind, key, data, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(layer, kind, key) DO UPDATE SET data = excluded.data, last_seen_at = excluded.last_seen_at",
            (entry["layer"], entry["kind"], entry["key"], json.dumps(entry, ensure_ascii=False),
             entry["first_seen_at"], entry["last_seen_at"]),
        )
        conn.commit()
    finally:
        conn.close()


def list_accumulated(layer: str, kind: Optional[str] = None) -> list[dict]:
    conn = _connect()
    try:
        if kind:
            rows = conn.execute("SELECT data FROM accumulated_entries WHERE layer = ? AND kind = ?", (layer, kind)).fetchall()
        else:
            rows = conn.execute("SELECT data FROM accumulated_entries WHERE layer = ?", (layer,)).fetchall()
        return [json.loads(r[0]) for r in rows]
    finally:
        conn.close()


def list_all_annotations() -> list[dict]:
    """Every prior annotation across all versions, oldest first (for vocabulary backfill)."""
    conn = _connect()
    try:
        rows = conn.execute("SELECT data FROM prior_annotations ORDER BY annotated_at ASC").fetchall()
        return [json.loads(r[0]) for r in rows]
    finally:
        conn.close()
