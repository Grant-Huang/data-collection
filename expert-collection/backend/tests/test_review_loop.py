"""Review loop for creating / editing a workflow (IMPLEMENTATION_PLAN.md section 17), with the
model replaced by scripted responses -- this checks the code-side guarantees (evidence
checking, validation before applying edits, undo, deterministic read-back, confirmation),
not model quality."""
import pytest

from app import llm_client, review_agent

NARRATIVE = ("设备报警以后，操作员先按急停，把这批零件隔离到待判区，然后叫质量工程师来复测。"
             "复测正常就恢复生产；确认超差的话，设备工程师查主轴和夹具，查完换刀试切首件，首件合格就恢复生产。")

EXTRACTED = {
    "nodes": [
        {"node_id": "n1", "node_type": "start", "label": "设备报警", "actor_roles": [], "evidence": "设备报警以后"},
        {"node_id": "n2", "node_type": "activity", "label": "按急停并隔离零件", "actor_roles": ["操作员"], "evidence": "操作员先按急停"},
        {"node_id": "n3", "node_type": "activity", "label": "质量工程师复测", "actor_roles": ["质量工程师"], "evidence": "叫质量工程师来复测"},
        {"node_id": "n4", "node_type": "decision", "label": "是否超差", "actor_roles": [], "evidence": "确认超差的话"},
        {"node_id": "n5", "node_type": "activity", "label": "检查主轴和夹具", "actor_roles": ["设备工程师"], "evidence": "设备工程师查主轴和夹具"},
        # Not something the expert said -> must be flagged, not trusted.
        {"node_id": "n6", "node_type": "activity", "label": "填写异常报告", "actor_roles": [], "evidence": "填写异常报告单"},
        {"node_id": "n7", "node_type": "end", "label": "恢复生产", "actor_roles": [], "evidence": "恢复生产"},
    ],
    "edges": [
        {"edge_id": "e1", "from": "n1", "to": "n2", "edge_type": "normal"},
        {"edge_id": "e2", "from": "n2", "to": "n3", "edge_type": "normal"},
        {"edge_id": "e3", "from": "n3", "to": "n4", "edge_type": "normal"},
        {"edge_id": "e4", "from": "n4", "to": "n7", "edge_type": "conditional", "condition": "复测正常"},
        {"edge_id": "e5", "from": "n4", "to": "n5", "edge_type": "conditional", "condition": "确认超差"},
        {"edge_id": "e6", "from": "n5", "to": "n6", "edge_type": "normal"},
        {"edge_id": "e7", "from": "n6", "to": "n7", "edge_type": "normal"},
    ],
    "start_node_ids": ["n1"], "end_node_ids": ["n7"],
    "summary": "设备报警后先停机隔离，复测后按结果恢复生产或查设备。",
    "uncertainties": [{"question": "换刀之后试切首件是谁来确认的？", "node_ids": ["n5"]}],
    "case_context": {"scenario_trigger": "设备报警", "scenario_goal": None},
}


class FakeModel:
    def __init__(self):
        self.review_responses: list = []
        self.calls: list[str] = []

    def __call__(self, cfg, messages, timeout=None):
        system = messages[0]["content"]
        if "流程整理模块" in system:
            self.calls.append("extract")
            return EXTRACTED
        self.calls.append("review")
        nxt = self.review_responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


@pytest.fixture
def model(monkeypatch):
    fake = FakeModel()
    monkeypatch.setattr(review_agent, "_slot", lambda slot: {"enabled": True, "endpoint": "http://x", "model_name": "m", "api_key": "k"})
    monkeypatch.setattr(llm_client, "chat_completion_json", fake)
    return fake


def _turn(client, wid, text):
    r = client.post(f"/api/expert-workflows/{wid}/turns", json={"text": text})
    assert r.status_code == 200, r.text
    return client.get(f"/api/expert-workflows/{wid}").json()


def _labels(rec):
    return {n["label"] for n in rec["graph"]["nodes"]}


def test_create_without_model_falls_back_to_step_guide(client):
    rec = client.post("/api/expert-workflows", json={}).json()
    assert not rec["stage"].startswith("review_")


def test_narrate_extract_clarify_confirm(client, model):
    rec = client.post("/api/expert-workflows", json={}).json()
    assert rec["stage"] == "review_narrative"
    assert rec["turns"][0]["sample"]  # sample narration shown, no chips
    assert not rec["turns"][0].get("chips")

    rec = _turn(client, rec["id"], "我讲一下设备报警怎么处理")  # too short: ask for the full story, no model call
    assert model.calls == [] and rec["stage"] == "review_narrative"

    rec = _turn(client, rec["id"], NARRATIVE)
    wid = rec["id"]
    assert model.calls == ["extract"] and rec["stage"] == "review_review"
    nodes = {n["label"]: n for n in rec["graph"]["nodes"]}
    assert nodes["按急停并隔离零件"]["evidence"] == ["操作员先按急停"]
    assert nodes["填写异常报告"]["evidence"] == []  # quote not in the narration -> unverified
    reply = rec["turns"][-1]
    assert reply["ack"] == EXTRACTED["summary"]
    assert "填写异常报告" in reply["question"]  # unverified step is asked about first
    assert rec["case_context"]["scenario_trigger"] == "设备报警"

    # Expert: that step doesn't exist; also after checking the spindle they swap the tool.
    model.review_responses.append({
        "intent": "edit", "understanding": "您是说没有填异常报告这一步。",
        "ops": [{"op": "remove_node", "node_id": "n6"},
                {"op": "add_node", "node": {"node_id": "x1", "node_type": "activity", "label": "换刀试切首件", "actor_roles": []}},
                {"op": "add_edge", "edge": {"edge_id": "a", "from": "n5", "to": "x1", "edge_type": "normal"}},
                {"op": "add_edge", "edge": {"edge_id": "b", "from": "x1", "to": "n7", "edge_type": "normal"}}],
        "evidence": {"x1": "换刀试切首件"},
        "resolved_gap_ids": [], "question": None, "new_uncertainties": [],
    })
    rec = _turn(client, wid, "没有填报告这一步，查完主轴就换刀试切首件")
    assert "填写异常报告" not in _labels(rec) and "换刀试切首件" in _labels(rec)
    new = next(n for n in rec["graph"]["nodes"] if n["label"] == "换刀试切首件")
    assert new["node_id"] != "x1" and new["evidence"] == ["换刀试切首件"]
    assert new["source_turn_ids"] == [rec["turns"][-2]["turn_id"]]  # "图上 +N" points at this turn
    changes = rec["turns"][-1]["changes"]
    assert any("删除步骤「填写异常报告」" in c for c in changes) and any("新增步骤「换刀试切首件」" in c for c in changes)

    # Edits that would create a cycle are refused as a whole; graph unchanged.
    model.review_responses.append({
        "intent": "edit", "understanding": "…",
        "ops": [{"op": "add_edge", "edge": {"edge_id": "c", "from": "n7", "to": "n1", "edge_type": "normal"}}],
        "evidence": {}, "resolved_gap_ids": [], "question": None, "new_uncertainties": [],
    })
    before = rec["graph"]
    rec = _turn(client, wid, "做完再回到开头")
    assert rec["graph"] == before and "没有改图" in rec["turns"][-1]["body"]

    # Undo restores the graph before the last applied edit.
    rec = _turn(client, wid, "撤销")
    assert "填写异常报告" in _labels(rec)
    assert len(model.review_responses) == 0  # undo needed no model call

    # A bare "对" answering a pending question is not "satisfied": it goes to the model.
    model.review_responses.append({"intent": "answer", "understanding": "好的。", "ops": [], "evidence": {},
                                   "resolved_gap_ids": [], "question": None, "new_uncertainties": []})
    calls = len(model.calls)
    rec = _turn(client, wid, "对")
    assert len(model.calls) == calls + 1
    assert rec["stage"] == "review_review"  # still clarifying, not jumped to the final read-back

    # Satisfied -> deterministic read-back from the graph -> confirm.
    rec = _turn(client, wid, "没问题了")
    assert rec["stage"] == "review_final_confirm" and rec["status"] == "needs_confirmation"
    body = rec["turns"][-1]["body"]
    assert "1. 设备报警" in body and "复测正常 → 恢复生产" in body
    rec = _turn(client, wid, "确认")
    assert rec["status"] == "expert_confirmed" and rec["stage"] == "review_done"
    assert all(n["expert_confirmed"] for n in rec["graph"]["nodes"])


def test_model_failure_changes_nothing(client, model):
    rec = client.post("/api/expert-workflows", json={}).json()
    rec = _turn(client, rec["id"], NARRATIVE)
    model.review_responses.append(llm_client.LLMError("timeout", "推理服务请求超时"))
    before = rec["graph"]
    rec = _turn(client, rec["id"], "第三步其实是班长做的")
    assert rec["graph"] == before and "暂时出错" in rec["turns"][-1]["body"]


def test_clarification_cap_moves_to_readback(client, model, monkeypatch):
    from app import settings as app_settings
    app_settings.save_settings({"review": {"max_clarify_questions": 1}})
    rec = client.post("/api/expert-workflows", json={}).json()
    rec = _turn(client, rec["id"], NARRATIVE)  # first question asked (1/1)
    model.review_responses.append({"intent": "answer", "understanding": "明白。", "ops": [], "evidence": {},
                                   "resolved_gap_ids": [], "question": None, "new_uncertainties": []})
    rec = _turn(client, rec["id"], "那一步是我说错了，没有")
    assert rec["stage"] == "review_final_confirm"  # cap reached -> read-back, no more questions


def test_reopen_confirmed_workflow_for_editing(client, model):
    rec = client.post("/api/expert-workflows", json={}).json()
    wid = rec["id"]
    _turn(client, wid, NARRATIVE)
    _turn(client, wid, "没问题")
    rec = _turn(client, wid, "确认")
    assert rec["status"] == "expert_confirmed"
    r = client.post(f"/api/expert-workflows/{wid}/reopen")
    assert r.status_code == 200
    rec = r.json()
    assert rec["status"] == "collecting" and rec["stage"] == "review_review"
    assert "这是目前的流程" in rec["turns"][-1]["body"]
