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
