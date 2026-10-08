"""C5: dataset code reads only the fields it needs, straight out of SQLite, and gets exactly what
parsing the full record would have given it."""
from app import dataset_records, db


def _make(client, name):
    rec = client.post("/api/expert-workflows", json={"name": name}).json()
    client.post(f"/api/expert-workflows/{rec['id']}/turns", json={"text": "设备报警了，操作员按急停。"})
    return db.get(rec["id"])


def test_get_fields_matches_the_full_record(client):
    a, b = _make(client, "甲"), _make(client, "乙")
    fields = ("id", "name", "graph", "case_context", "task_workflow")
    got = db.get_fields([b["id"], "missing", a["id"]], fields)
    assert set(got) == {a["id"], b["id"]}
    for full in (a, b):
        assert got[full["id"]] == {f: full.get(f) for f in fields}


def test_records_for_export_and_record_ids_keep_version_order(client):
    a, b = _make(client, "甲"), _make(client, "乙")
    version = {"source_type": "expert_collected", "workflow_ids": [b["id"], "gone", a["id"]]}
    assert dataset_records.record_ids(version) == [b["id"], a["id"]]
    records = dataset_records.records_for_export(version)
    assert [r["record_id"] for r in records] == [b["id"], a["id"]]
    assert records[0]["graph"] == b["graph"] and records[0]["scenario"]["scenario_name"] == "乙"


def test_schema_is_created_once_per_db_file(client, monkeypatch, tmp_path):
    _make(client, "甲")
    calls = []
    real = db._create_schema
    monkeypatch.setattr(db, "_create_schema", lambda conn: (calls.append(1), real(conn)))
    db.list_summaries()
    assert calls == []  # this file already has its schema
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "other.db")
    db.list_summaries()
    db.list_summaries()
    assert calls == [1]


def _version(vid, ids, created, **extra):
    return {"id": vid, "source_type": "public_extracted", "version_number": 1, "workflow_ids": ids,
            "created_at": created, "records": [{"record_id": i, "graph": {}} for i in ids], **extra}


def test_dataset_references_come_from_the_id_column(monkeypatch):
    """Opening a session checks "already in a dataset?" -- it must not parse every version blob
    (an imported dataset carries all of its records inline)."""
    db.save_dataset_version(_version("v1", ["a", "b"], "2026-10-01T00:00:00Z"))
    db.save_dataset_version(_version("v2", ["b"], "2026-10-02T00:00:00Z"))
    db.archive_dataset_version("v1")
    monkeypatch.setattr(db, "list_dataset_versions", lambda *a, **k: (_ for _ in ()).throw(AssertionError("parsed blobs")))
    assert dataset_records.versions_containing("b") == [
        {"id": "v2", "source_type": "public_extracted", "version_number": 1, "archived": False},
        {"id": "v1", "source_type": "public_extracted", "version_number": 1, "archived": True},
    ]
    assert dataset_records.versions_containing("zzz") == []
    assert dataset_records.published_workflow_ids() == {"a", "b"}


def test_rows_saved_before_the_id_column_existed_are_backfilled(tmp_path, monkeypatch):
    import json, sqlite3
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE dataset_versions (id TEXT PRIMARY KEY, source_type TEXT NOT NULL, "
                 "version_number INTEGER NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL, "
                 "archived INTEGER NOT NULL DEFAULT 0)")
    old = _version("old", ["x", "y"], "2026-09-01T00:00:00Z")
    conn.execute("INSERT INTO dataset_versions (id, source_type, version_number, data, created_at) VALUES (?, ?, ?, ?, ?)",
                 ("old", "public_extracted", 1, json.dumps(old), old["created_at"]))
    conn.execute("INSERT INTO dataset_versions (id, source_type, version_number, data, created_at) VALUES (?, ?, ?, ?, ?)",
                 ("noids", "public_extracted", 2, json.dumps({"id": "noids"}), "2026-09-02T00:00:00Z"))
    conn.commit(); conn.close()
    monkeypatch.setattr(db, "DB_PATH", path)
    assert [v["id"] for v in dataset_records.versions_containing("y")] == ["old"]
    assert dataset_records.published_workflow_ids() == {"x", "y"}
