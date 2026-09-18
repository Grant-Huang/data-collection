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
            created_at TEXT NOT NULL
        )
        """
    )
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
