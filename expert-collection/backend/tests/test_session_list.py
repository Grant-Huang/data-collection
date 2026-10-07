"""Session list reads only the small per-row summary, never the full records (C4), and keeps
showing the same thing it did before."""
import json

from app import db


def _make(client, name):
    return client.post("/api/expert-workflows", json={"name": name}).json()


def test_list_matches_the_record_and_hides_archived_by_default(client):
    a = _make(client, "会话 A")
    b = _make(client, "会话 B")
    client.patch(f"/api/expert-workflows/{b['id']}", json={"archived": True})

    rows = client.get("/api/expert-workflows").json()
    assert [r["id"] for r in rows] == [a["id"]]
    row = rows[0]
    assert (row["name"], row["status"], row["completion_score"], row["archived"], row["pinned"]) == (
        "会话 A", a["status"], a["completion"]["score"], False, False)

    rows = client.get("/api/expert-workflows", params={"include_archived": True}).json()
    assert {r["id"] for r in rows} == {a["id"], b["id"]}


def test_pinned_first_then_newest(client):
    first = _make(client, "最早")
    _make(client, "中间")
    last = _make(client, "最新")
    client.patch(f"/api/expert-workflows/{first['id']}", json={"pinned": True})

    rows = client.get("/api/expert-workflows").json()
    assert rows[0]["id"] == first["id"] and rows[0]["pinned"]
    assert rows[1]["id"] == last["id"]


def test_summary_tracks_later_changes(client):
    rec = _make(client, "原名")
    client.patch(f"/api/expert-workflows/{rec['id']}", json={"name": "改过的名字"})
    client.post(f"/api/expert-workflows/{rec['id']}/turns", json={"text": "设备报警了，操作员按急停。"})

    row = client.get("/api/expert-workflows").json()[0]
    full = client.get(f"/api/expert-workflows/{rec['id']}").json()
    assert row["name"] == "改过的名字"
    assert (row["status"], row["completion_score"], row["updated_at"]) == (
        full["status"], full["completion"]["score"], full["updated_at"])


def test_list_does_not_read_the_big_blobs(client, monkeypatch):
    _make(client, "会话")
    monkeypatch.setattr(db, "list_all", lambda: (_ for _ in ()).throw(AssertionError("list_all() reads every full record")))
    assert len(client.get("/api/expert-workflows").json()) == 1


def test_rows_written_before_the_summary_column_are_backfilled(client):
    rec = _make(client, "老记录")
    conn = db._connect()
    conn.execute("UPDATE workflows SET summary = NULL WHERE id = ?", (rec["id"],))
    conn.commit()
    conn.close()

    row = client.get("/api/expert-workflows").json()[0]
    assert row["name"] == "老记录" and row["completion_score"] == rec["completion"]["score"]

    # Backfilled once and persisted, so the next read doesn't parse the record again.
    conn = db._connect()
    stored = conn.execute("SELECT summary FROM workflows WHERE id = ?", (rec["id"],)).fetchone()[0]
    conn.close()
    assert json.loads(stored)["name"] == "老记录"


# --- B2: soft delete, the four tabs, auto-naming ---------------------------------------------

def test_soft_delete_hides_from_default_list_and_can_be_restored(client):
    keep = _make(client, "留下")
    gone = _make(client, "删掉")
    client.patch(f"/api/expert-workflows/{gone['id']}", json={"pinned": True})
    rec = client.patch(f"/api/expert-workflows/{gone['id']}", json={"deleted": True}).json()
    # Deleting drops the pin so a deleted session never floats to the top.
    assert rec["deleted"] is True and rec["pinned"] is False

    assert [r["id"] for r in client.get("/api/expert-workflows").json()] == [keep["id"]]
    # Archived alone does not bring deleted ones back; only include_deleted does.
    assert gone["id"] not in {r["id"] for r in client.get("/api/expert-workflows", params={"include_archived": True}).json()}
    rows = client.get("/api/expert-workflows", params={"include_archived": True, "include_deleted": True}).json()
    assert {r["id"]: r["deleted"] for r in rows} == {keep["id"]: False, gone["id"]: True}

    # Soft delete only: the record is still readable, and restoring brings it back.
    assert client.get(f"/api/expert-workflows/{gone['id']}").status_code == 200
    client.patch(f"/api/expert-workflows/{gone['id']}", json={"deleted": False})
    assert {r["id"] for r in client.get("/api/expert-workflows").json()} == {keep["id"], gone["id"]}


def test_deleted_confirmed_session_stays_out_of_the_draft_pool(client):
    rec = _make(client, "已确认")
    stored = db.get(rec["id"])
    stored["status"] = "expert_confirmed"
    db.save(stored)
    assert client.get("/api/datasets/draft-pool").json()["count"] == 1

    client.patch(f"/api/expert-workflows/{rec['id']}", json={"deleted": True})
    assert client.get("/api/datasets/draft-pool").json()["count"] == 0


def test_default_name_becomes_the_first_sentence(client):
    rec = client.post("/api/expert-workflows", json={}).json()
    assert rec["name"].startswith("专家会话 ")
    client.post(f"/api/expert-workflows/{rec['id']}/turns", json={"text": "主轴温度报警后的处理，一般先停机。"})
    assert client.get(f"/api/expert-workflows/{rec['id']}").json()["name"] == "主轴温度报警后的处理"

    # Only the first expert message names it; later ones don't rename.
    client.post(f"/api/expert-workflows/{rec['id']}/turns", json={"text": "另外一件事。"})
    assert client.get(f"/api/expert-workflows/{rec['id']}").json()["name"] == "主轴温度报警后的处理"


def test_long_first_sentence_is_cut_and_chosen_names_are_kept(client):
    rec = client.post("/api/expert-workflows", json={}).json()
    long = "设备报警以后操作员先按急停然后隔离零件再叫质量工程师复测"
    client.post(f"/api/expert-workflows/{rec['id']}/turns", json={"text": long})
    name = client.get(f"/api/expert-workflows/{rec['id']}").json()["name"]
    assert name == long[:18] + "…"

    named = _make(client, "我起的名字")
    client.post(f"/api/expert-workflows/{named['id']}/turns", json={"text": "主轴温度报警后的处理。"})
    assert client.get(f"/api/expert-workflows/{named['id']}").json()["name"] == "我起的名字"
