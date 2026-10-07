"""Stable per-node step numbers (`Node.seq`) so a person -- and the review-loop model -- can
say "第3步" and have it mean exactly one node, for the life of a conversation.

Unlike readback()'s old behaviour (recomputed fresh every call from topological order), `seq`
is assigned once, at creation, and never touched again: see graph_ops.assign_missing_seqs and
its one caller, apply_ops (covers every ops-based edit) plus guide_service._coerce_regenerated_
graph (covers narrative extraction / full regenerate) and the import/get_workflow backfills for
data that predates the field.
"""
import pytest

from app import graph_ops, guide_service, llm_client, review_agent


def _node(nid, seq=None):
    n = {"node_id": nid, "node_type": "activity", "label": nid, "actor_roles": []}
    if seq is not None:
        n["seq"] = seq
    return n


def test_assign_missing_seqs_numbers_only_the_gaps_in_list_order():
    graph = {"nodes": [_node("a"), _node("b"), _node("c")], "edges": []}
    graph_ops.assign_missing_seqs(graph)
    assert [n["seq"] for n in graph["nodes"]] == [1, 2, 3]


def test_assign_missing_seqs_never_touches_an_existing_seq_and_continues_past_the_max():
    graph = {"nodes": [_node("a", seq=5), _node("b"), _node("c", seq=1)], "edges": []}
    graph_ops.assign_missing_seqs(graph)
    assert [n["seq"] for n in graph["nodes"]] == [5, 6, 1]  # "b" continues from the max (5), not from 3


def test_apply_ops_assigns_seq_to_new_nodes_and_never_renumbers_survivors():
    graph = graph_ops.new_graph()
    graph_ops.apply_ops(graph, [
        {"op": "add_node", "node": _node("a")},
        {"op": "add_node", "node": _node("b")},
    ])
    a_seq = next(n["seq"] for n in graph["nodes"] if n["node_id"] == "a")
    assert a_seq == 1

    # Renaming "a" and deleting "b" must not touch a's number; a node added afterward gets a
    # fresh, higher number rather than reusing "b"'s old one.
    graph_ops.apply_ops(graph, [
        {"op": "update_node", "node_id": "a", "patch": {"label": "新名字"}},
        {"op": "remove_node", "node_id": "b"},
        {"op": "add_node", "node": _node("c")},
    ])
    by_id = {n["node_id"]: n for n in graph["nodes"]}
    assert by_id["a"]["seq"] == a_seq and by_id["a"]["label"] == "新名字"
    assert "b" not in by_id
    assert by_id["c"]["seq"] > a_seq


NARRATIVE = ("设备报警以后，操作员先按急停，把这批零件隔离到待判区，然后叫质量工程师来复测。"
             "复测正常就恢复生产；确认超差的话，设备工程师查主轴和夹具，查完换刀试切首件，首件合格就恢复生产。")
EXTRACTED = {
    "nodes": [
        {"node_id": "n1", "node_type": "start", "label": "设备报警", "actor_roles": [], "evidence": "设备报警以后"},
        {"node_id": "n2", "node_type": "activity", "label": "按急停", "actor_roles": ["操作员"], "evidence": "操作员先按急停"},
        {"node_id": "n3", "node_type": "activity", "label": "质量工程师复测", "actor_roles": ["质量工程师"], "evidence": "质量工程师复测"},
        {"node_id": "n4", "node_type": "end", "label": "恢复生产", "actor_roles": [], "evidence": "恢复生产"},
    ],
    "edges": [
        {"edge_id": "e1", "from": "n1", "to": "n2", "edge_type": "normal"},
        {"edge_id": "e2", "from": "n2", "to": "n3", "edge_type": "normal"},
        {"edge_id": "e3", "from": "n3", "to": "n4", "edge_type": "normal"},
    ],
    "start_node_ids": ["n1"], "end_node_ids": ["n4"],
    "summary": "设备报警后停机复测，合格恢复生产。", "uncertainties": [], "case_context": {},
}


@pytest.fixture
def model(monkeypatch):
    calls = []

    def fake(cfg, messages, timeout=None):
        calls.append(messages[0]["content"])
        return EXTRACTED

    monkeypatch.setattr(review_agent, "_slot", lambda slot: {"enabled": True, "endpoint": "http://x", "model_name": "m", "api_key": "k"})
    monkeypatch.setattr(llm_client, "chat_completion_json", fake)
    return calls


def test_narrative_extraction_numbers_nodes_in_narration_order(client, model):
    rec = client.post("/api/expert-workflows", json={}).json()
    rec = client.post(f"/api/expert-workflows/{rec['id']}/turns", json={"text": NARRATIVE}).json()["current_dag"]
    seqs = {n["label"]: n["seq"] for n in rec["nodes"]}
    assert seqs == {"设备报警": 1, "按急停": 2, "质量工程师复测": 3, "恢复生产": 4}


def test_graph_for_prompt_carries_seq_for_the_model_to_resolve_ordinal_references():
    graph = {"nodes": [_node("n1", seq=1), _node("n2", seq=2)], "edges": []}
    sent = review_agent._graph_for_prompt(graph)
    assert '"seq": 1' in sent and '"seq": 2' in sent


def test_readback_numbers_lines_by_seq_not_by_recomputed_position():
    graph = {
        "nodes": [
            {"node_id": "n1", "node_type": "start", "label": "开始", "actor_roles": [], "seq": 1},
            # Inserted later, between n1 and n2 -- topological walk order puts it second, but
            # its seq (assigned when it was created) is 3, and that's what must be shown.
            {"node_id": "n3", "node_type": "activity", "label": "插入的步骤", "actor_roles": [], "seq": 3},
            {"node_id": "n2", "node_type": "end", "label": "结束", "actor_roles": [], "seq": 2},
        ],
        "edges": [
            {"edge_id": "e1", "from": "n1", "to": "n3", "edge_type": "normal"},
            {"edge_id": "e2", "from": "n3", "to": "n2", "edge_type": "normal"},
        ],
        "start_node_ids": ["n1"], "end_node_ids": ["n2"],
    }
    body = review_agent.readback(graph)
    assert "1. 开始" in body and "3. 插入的步骤" in body and "2. 结束" in body


def test_import_backfills_seq_for_uploaded_records(client, tmp_path):
    import copy
    import json
    from pathlib import Path

    sample = json.loads((Path(__file__).resolve().parents[3] / "docs/expert-workflow-collection/schema/workflow_graph_v2_sample.json").read_text())
    record = copy.deepcopy(sample["records"][0])
    for n in record["graph"]["nodes"]:
        n.pop("seq", None)  # simulate an uploaded file, which never has this field
    record.setdefault("provenance", {})["source_type"] = "public_extracted"
    payload = {"dataset_meta": {**sample["dataset_meta"], "source_type": "public_extracted"}, "records": [record]}
    res = client.post("/api/datasets/import/confirm", json={"payload": payload, "import_records_without_errors": True})
    assert res.status_code == 200, res.text
    version_id = res.json()["id"]
    rec = client.get(f"/api/datasets/versions/{version_id}/records/{record['record_id']}").json()
    seqs = [n["seq"] for n in rec["graph"]["nodes"]]
    assert all(isinstance(s, int) for s in seqs) and len(set(seqs)) == len(seqs)


def test_get_workflow_backfills_legacy_graphs_without_seq(client):
    rec = client.post("/api/expert-workflows", json={}).json()
    wid = rec["id"]
    # Simulate a workflow collected before `seq` existed: give it some nodes the way it would
    # have looked on disk back then -- no `seq` key at all.
    from app import db
    stored = db.get(wid)
    stored["graph"]["nodes"] = [_node("n1"), _node("n2")]
    db.save(stored)

    fetched = client.get(f"/api/expert-workflows/{wid}").json()
    seqs = [n["seq"] for n in fetched["graph"]["nodes"]]
    assert all(isinstance(s, int) for s in seqs)
    # Persisted, not recomputed per request -- a second read returns the exact same numbers.
    again = client.get(f"/api/expert-workflows/{wid}").json()
    assert [n["seq"] for n in again["graph"]["nodes"]] == seqs
