"""Manual drag persistence (DagView's onNodeMove -> PATCH .../nodes/{node_id}/position).

Checks the table from the design discussion: a drag sets manual_position; nothing else does or
can (the LLM's update_node patch whitelist in review_agent.sanitize_ops never includes
position, so this endpoint is the only path that ever writes it).
"""
from app import guide_service


def _turn(client, wid, text):
    r = client.post(f"/api/expert-workflows/{wid}/turns", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


def _record(client, wid):
    return client.get(f"/api/expert-workflows/{wid}").json()


def _some_workflow_with_nodes(client):
    wid = client.post("/api/expert-workflows", json={}).json()["id"]
    _turn(client, wid, "设备/质量异常")
    _turn(client, wid, "CNC 加工件尺寸超差，质检抽检发现的")
    _turn(client, wid, guide_service.GOAL_SKIP_CHIP)
    _turn(client, wid, "无")
    _turn(client, wid, "班组长先停机")
    return wid


def test_drag_persists_and_survives_an_unrelated_llm_edit(client):
    wid = _some_workflow_with_nodes(client)
    node_id = _record(client, wid)["graph"]["nodes"][0]["node_id"]

    r = client.patch(f"/api/expert-workflows/{wid}/nodes/{node_id}/position", json={"x": 123.5, "y": 67.0})
    assert r.status_code == 200 and r.json() == {"ok": True}

    rec = _record(client, wid)
    moved = next(n for n in rec["graph"]["nodes"] if n["node_id"] == node_id)
    assert moved["manual_position"] == {"x": 123.5, "y": 67.0}

    # A later, unrelated turn (content only) must not touch the pinned position.
    _turn(client, wid, "质检员复测尺寸，如果尺寸超差就要返工")
    rec = _record(client, wid)
    moved = next(n for n in rec["graph"]["nodes"] if n["node_id"] == node_id)
    assert moved["manual_position"] == {"x": 123.5, "y": 67.0}


def test_new_nodes_have_no_manual_position(client):
    wid = _some_workflow_with_nodes(client)
    rec = _record(client, wid)
    assert all(n["manual_position"] is None for n in rec["graph"]["nodes"])


def test_position_404s_for_missing_workflow_or_node(client):
    wid = _some_workflow_with_nodes(client)
    node_id = _record(client, wid)["graph"]["nodes"][0]["node_id"]
    assert client.patch(f"/api/expert-workflows/does-not-exist/nodes/{node_id}/position", json={"x": 0, "y": 0}).status_code == 404
    assert client.patch(f"/api/expert-workflows/{wid}/nodes/does-not-exist/position", json={"x": 0, "y": 0}).status_code == 404
