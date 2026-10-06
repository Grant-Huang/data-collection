"""Editing the read-back in place (「修改这段流程」): the expert gets the numbered, tagged
read-back in the input box, edits it and sends it back. Lines are aligned with the read-back
they came from by number, in code; numbers and tags are read-only; the model only interprets
changed / added lines. Model replaced by scripted responses, as in test_review_loop."""
import copy

import pytest

from app import graph_ops, graph_validator, llm_client, readback_edit, review_agent
from tests.test_dag_shape import GOOD, NARRATIVE, _connected_head_to_tail, _e, _graph


class Model:
    def __init__(self):
        self.queue: list = []
        self.review_inputs: list[str] = []

    def __call__(self, cfg, messages, timeout=None):
        if "流程整理模块" in messages[0]["content"]:
            return copy.deepcopy(GOOD)
        self.review_inputs.append(messages[1]["content"])
        return self.queue.pop(0)


@pytest.fixture
def model(monkeypatch):
    fake = Model()
    monkeypatch.setattr(review_agent, "_slot", lambda slot: {"enabled": True, "endpoint": "http://x", "model_name": "m", "api_key": "k"})
    monkeypatch.setattr(llm_client, "chat_completion_json", fake)
    return fake


def _send(client, wid, text, from_readback=False):
    r = client.post(f"/api/expert-workflows/{wid}/turns", json={"text": text, "from_readback": from_readback})
    assert r.status_code == 200, r.text
    return client.get(f"/api/expert-workflows/{wid}").json()


def _at_readback(client):
    """A workflow drafted from GOOD and taken to the final read-back."""
    rec = client.post("/api/expert-workflows", json={}).json()
    wid = rec["id"]
    _send(client, wid, NARRATIVE)
    rec = _send(client, wid, "没问题")
    assert rec["stage"] == "review_final_confirm"
    return wid, rec, rec["turns"][-1]["readback"]


def _line(readback, seq):
    return next(l for l in readback.splitlines() if l.startswith(f"[{seq}]"))


def _edit(ops, understanding="好的"):
    return {"intent": "edit", "understanding": understanding, "ops": ops, "evidence": {},
            "resolved_gap_ids": [], "question": None, "new_uncertainties": []}


# --- rendering ------------------------------------------------------------------------------

def test_readback_lines_carry_number_and_type_tag():
    text = review_agent.readback(_graph())
    assert text.splitlines()[0] == "[1]【开始】设备报警"
    assert "[4]【判断】复测结果：复测正常 → [8]；确认超差 → [5]" in text
    assert "[2]按急停并隔离零件" in text  # a plain step has no tag
    assert "[8]【结束】恢复生产" in text


def test_assistant_turn_exposes_the_editable_readback(client, model):
    _, rec, rb = _at_readback(client)
    assert rb and rb in rec["turns"][-1]["body"]


# --- the edit round trip --------------------------------------------------------------------

def test_changed_line_reaches_the_model_with_its_node_id(client, model):
    wid, _, rb = _at_readback(client)
    edited = rb.replace(_line(rb, 6), "[6]换刀并调程序参数（工艺员）")
    model.queue.append(_edit([{"op": "update_node", "node_id": "n6",
                               "patch": {"label": "换刀并调程序参数", "actor_roles": ["工艺员"]}}]))
    rec = _send(client, wid, edited, from_readback=True)
    assert "修改 [6]（node_id=n6）：原来「换刀」→ 现在「换刀并调程序参数（工艺员）」" in model.review_inputs[-1]
    n6 = next(n for n in rec["graph"]["nodes"] if n["node_id"] == "n6")
    assert n6["label"] == "换刀并调程序参数" and n6["actor_roles"] == ["工艺员"]
    # Unchanged lines are not reported to the model as changes.
    assert "修改 [5]" not in model.review_inputs[-1]


def test_deleted_line_removes_the_step_without_a_model_call(client, model):
    wid, _, rb = _at_readback(client)
    edited = "\n".join(l for l in rb.splitlines() if not l.startswith("[6]"))
    rec = _send(client, wid, edited, from_readback=True)
    assert model.review_inputs == []
    assert "换刀" not in {n["label"] for n in rec["graph"]["nodes"]}
    assert _connected_head_to_tail(rec["graph"]) and graph_validator.is_valid(rec["graph"])
    assert any("删除步骤「换刀」" in c for c in rec["turns"][-1]["changes"])


def test_added_line_is_positioned_between_its_numbered_neighbours(client, model):
    wid, _, rb = _at_readback(client)
    edited = rb.replace(_line(rb, 6), _line(rb, 6) + "\n通知班组长到场")
    model.queue.append(_edit([
        {"op": "add_node", "node": {"node_id": "x", "node_type": "activity", "label": "通知班组长到场", "actor_roles": []}},
        {"op": "add_edge", "edge": _e("a", "n6", "x")}]))
    rec = _send(client, wid, edited, from_readback=True)
    assert "新增一行（位于[6] 之后、[7] 之前）：「通知班组长到场」" in model.review_inputs[-1]
    g = rec["graph"]
    new = next(n["node_id"] for n in g["nodes"] if n["label"] == "通知班组长到场")
    assert {(e["from"], e["to"]) for e in g["edges"]} >= {("n6", new), (new, "n7")}


@pytest.mark.parametrize("mutate, expect", [
    (lambda rb: rb.replace("[4]【判断】", "[4]【审批】"), "编号 [4] 的标签被改了"),
    (lambda rb: rb.replace("[6]", "[60]"), "编号 [60] 在原来的流程里不存在"),
    (lambda rb: rb + "\n" + _line(rb, 3), "编号 [3] 出现了两次"),
    (lambda rb: rb.replace("[1]【开始】", "[1]"), "编号 [1] 的标签被改了"),
])
def test_altered_numbers_or_tags_are_refused(client, model, mutate, expect):
    wid, rec, rb = _at_readback(client)
    before = rec["graph"]
    rec = _send(client, wid, mutate(rb), from_readback=True)
    body = rec["turns"][-1]["body"]
    assert expect in body and "不能改" in body
    assert rec["graph"] == before and model.review_inputs == []


def test_unchanged_copy_is_not_an_edit(client, model):
    wid, rec, rb = _at_readback(client)
    rec = _send(client, wid, rb, from_readback=True)
    assert "没看到改动" in rec["turns"][-1]["body"] and model.review_inputs == []


def test_stale_copy_never_edits_a_changed_graph(client, model):
    wid, _, rb = _at_readback(client)
    # The graph changes after that read-back was shown (an ordinary spoken edit)...
    model.queue.append(_edit([{"op": "update_node", "node_id": "n2", "patch": {"label": "按急停"}}]))
    _send(client, wid, "第2步只是按急停")
    # ...then the old copy is sent back.
    rec = client.get(f"/api/expert-workflows/{wid}").json()
    before = rec["graph"]
    rec = _send(client, wid, "\n".join(l for l in rb.splitlines() if not l.startswith("[6]")), from_readback=True)
    assert "之前那一版" in rec["turns"][-1]["body"] and rec["graph"] == before


# --- numbers are stable and never reused ----------------------------------------------------

def test_deleted_number_is_never_handed_out_again():
    g = _graph()
    top = max(n["seq"] for n in g["nodes"])
    top_node = next(n["node_id"] for n in g["nodes"] if n["seq"] == top)
    graph_ops.apply_ops(g, [{"op": "remove_node", "node_id": top_node},
                            {"op": "add_node", "node": {"node_id": "new", "node_type": "activity", "label": "新步骤"}}])
    assert next(n for n in g["nodes"] if n["node_id"] == "new")["seq"] == top + 1


def test_undo_does_not_rewind_the_number_counter(client, model):
    wid, _, rb = _at_readback(client)
    model.queue.append(_edit([
        {"op": "add_node", "node": {"node_id": "x", "node_type": "activity", "label": "通知班组长", "actor_roles": []}},
        {"op": "add_edge", "edge": _e("a", "n6", "x")}]))
    rec = _send(client, wid, "换刀后通知班组长")
    used = next(n["seq"] for n in rec["graph"]["nodes"] if n["label"] == "通知班组长")
    rec = _send(client, wid, "撤销")
    assert "通知班组长" not in {n["label"] for n in rec["graph"]["nodes"]}
    model.queue.append(_edit([
        {"op": "add_node", "node": {"node_id": "y", "node_type": "activity", "label": "拍照留证", "actor_roles": []}},
        {"op": "add_edge", "edge": _e("b", "n6", "y")}]))
    rec = _send(client, wid, "换刀后拍照留证")
    assert next(n["seq"] for n in rec["graph"]["nodes"] if n["label"] == "拍照留证") > used


# --- annotation (标定) uses the same path ---------------------------------------------------

def test_annotation_session_accepts_an_edited_readback(client, model):
    from tests.test_annotation_review import SAMPLE, _start
    payload = {"dataset_meta": {**SAMPLE["dataset_meta"], "source_type": "public_extracted"},
               "records": [{**copy.deepcopy(SAMPLE["records"][0]), "provenance": {"source_type": "public_extracted"}}]}
    vid = client.post("/api/datasets/import/confirm", json={"payload": payload, "import_records_without_errors": True}).json()["id"]
    rid = SAMPLE["records"][0]["record_id"]
    s = _start(client, vid, rid, "alice")
    rb = s["turns"][0]["readback"]
    seq9 = next(n["seq"] for n in s["graph"]["nodes"] if n["node_id"] == "n9")
    edited = "\n".join(l for l in rb.splitlines() if not l.startswith(f"[{seq9}]"))
    r = client.post(f"/api/datasets/versions/{vid}/review-sessions/{s['session_id']}/turns",
                    json={"text": edited, "from_readback": True})
    assert r.status_code == 200, r.text
    s = r.json()
    assert "n9" not in {n["node_id"] for n in s["graph"]["nodes"]}
    assert _connected_head_to_tail(s["graph"]) and graph_validator.is_valid(s["graph"])


# --- parser unit checks ---------------------------------------------------------------------

def test_parse_ignores_blank_lines_and_whitespace_only_changes():
    g = _graph()
    text, snap = readback_edit.render(g, review_agent._topo_order(g))
    spaced = "\n\n".join(l.replace("：", " ：", 1) if l.startswith("[4]") else l for l in text.splitlines())
    assert readback_edit.parse(spaced, snap).empty


def test_successful_edit_hands_back_a_fresh_editable_copy(client, model):
    wid, _, rb = _at_readback(client)
    rec = _send(client, wid, "\n".join(l for l in rb.splitlines() if not l.startswith("[6]")), from_readback=True)
    reply = rec["turns"][-1]
    assert reply["readback"] and "[6]" not in reply["readback"] and reply["readback"] in reply["body"]
    # ...and that fresh copy is accepted for the next round of edits.
    rec = _send(client, wid, "\n".join(l for l in reply["readback"].splitlines() if not l.startswith("[7]")),
                from_readback=True)
    assert "试切首件" not in {n["label"] for n in rec["graph"]["nodes"]}
