"""Ontology follow-ups in the narrate-first review loop (IMPLEMENTATION_PLAN.md section 17;
ontology design doc section 9): after the draft graph exists, the clarification list asks a
decision step for its threshold / expected value and an approval step for its time limit and
escalation target. The expert's answer is turned into node fields by code
(ontology_capture), not by the model -- the model is scripted here and never returns such
fields, so whatever shows up on the node came from the parser."""
import pytest

from app import llm_client, review_agent, review_gaps

NARRATIVE = ("换型以后先由操作员做首件，质量员测关键尺寸，尺寸合格的话交给工艺工程师签字放行，签完就批量生产；"
             "尺寸不合格就由操作员调整参数再做一件。")

EXTRACTED = {
    "nodes": [
        {"node_id": "n1", "node_type": "start", "label": "换型完成", "actor_roles": [], "evidence": "换型以后"},
        {"node_id": "n2", "node_type": "activity", "label": "做首件", "actor_roles": ["操作员"], "evidence": "先由操作员做首件"},
        {"node_id": "n3", "node_type": "activity", "label": "测关键尺寸", "actor_roles": ["质量员"], "evidence": "质量员测关键尺寸"},
        {"node_id": "n4", "node_type": "decision", "label": "尺寸是否合格", "actor_roles": [], "evidence": "尺寸合格的话",
         "decision_question": "关键尺寸合格吗"},
        {"node_id": "n5", "node_type": "approval", "label": "工艺工程师签字放行", "actor_roles": ["工艺工程师"], "evidence": "交给工艺工程师签字放行"},
        {"node_id": "n6", "node_type": "activity", "label": "调整参数", "actor_roles": ["操作员"], "evidence": "由操作员调整参数"},
        {"node_id": "n7", "node_type": "end", "label": "批量生产", "actor_roles": [], "evidence": "签完就批量生产"},
    ],
    "edges": [
        {"edge_id": "e1", "from": "n1", "to": "n2", "edge_type": "normal"},
        {"edge_id": "e2", "from": "n2", "to": "n3", "edge_type": "normal"},
        {"edge_id": "e3", "from": "n3", "to": "n4", "edge_type": "normal"},
        {"edge_id": "e4", "from": "n4", "to": "n5", "edge_type": "conditional", "condition": "尺寸合格"},
        {"edge_id": "e5", "from": "n4", "to": "n6", "edge_type": "conditional", "condition": "尺寸不合格"},
        {"edge_id": "e6", "from": "n5", "to": "n7", "edge_type": "normal"},
        {"edge_id": "e7", "from": "n6", "to": "n7", "edge_type": "normal"},
    ],
    "start_node_ids": ["n1"], "end_node_ids": ["n7"],
    "summary": "换型后做首件、测尺寸，合格就签字放行，不合格就调参数。",
    "uncertainties": [],
    "case_context": {},
}


def _answer():
    """A scripted review-model reply: the expert answered the pending question, nothing else."""
    return {"intent": "answer", "understanding": "明白了。", "ops": [], "evidence": {},
            "resolved_gap_ids": [], "question": None, "new_uncertainties": []}


class FakeModel:
    def __init__(self):
        self.review_responses: list = []

    def __call__(self, cfg, messages, timeout=None):
        if "流程整理模块" in messages[0]["content"]:
            return EXTRACTED
        return self.review_responses.pop(0)


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


def _narrate(client, wid, text=NARRATIVE):
    """Tell the story (one piece is enough here), then say 「讲完了」 -- the draft is only built
    on that signal, so the expert can tell it in several pieces."""
    _turn(client, wid, text)
    return _turn(client, wid, "讲完了")


def _node(rec, nid):
    return next(n for n in rec["graph"]["nodes"] if n["node_id"] == nid)


def _answer_until(client, model, rec, keyword, max_turns=10):
    """Answer pending questions with a neutral reply until the one containing `keyword` is asked."""
    for _ in range(max_turns):
        if keyword in (rec["turns"][-1].get("question") or ""):
            return rec
        model.review_responses.append(_answer())
        rec = _turn(client, rec["id"], "就是这样")
    raise AssertionError(f"never asked about {keyword!r}")


def test_rule_gaps_ask_decision_criterion_and_approval_timing():
    gaps = {g["id"]: g for g in review_gaps.rule_gaps(EXTRACTED, mode="create")}
    assert "尺寸是否合格" in gaps["criterion:n4"]["text"]
    assert "工艺工程师签字放行" in gaps["timing:n5"]["text"]
    # Not asked when reviewing someone else's graph (annotate / arbitrate).
    assert not any(g["kind"] in ("criterion", "timing") for g in review_gaps.rule_gaps(EXTRACTED, mode="annotate"))
    # Already captured -> not asked.
    graph = {**EXTRACTED, "nodes": [dict(n, evaluation_criteria=[{"id": "c1"}]) if n["node_id"] == "n4" else n
                                    for n in EXTRACTED["nodes"]]}
    assert "criterion:n4" not in {g["id"] for g in review_gaps.rule_gaps(graph, mode="create")}


def test_rule_gaps_cap_counts_steps():
    nodes = [{"node_id": f"d{i}", "node_type": "decision", "label": f"判断{i}"} for i in range(4)]
    graph = {"nodes": nodes, "edges": []}
    asked = [g["id"] for g in review_gaps.rule_gaps(graph, mode="create") if g["kind"] == "criterion"]
    assert asked == ["criterion:d0", "criterion:d1"]
    # Answering the first one does not pull a third step into the list.
    nodes[0]["evaluation_criteria"] = [{"id": "c1"}]
    asked = [g["id"] for g in review_gaps.rule_gaps(graph, mode="create") if g["kind"] == "criterion"]
    assert asked == ["criterion:d1"]


def test_answers_become_node_fields_and_ontology(client, model):
    rec = client.post("/api/expert-workflows", json={}).json()
    rec = _narrate(client, rec["id"])
    wid = rec["id"]
    assert rec["stage"] == "review_review"

    rec = _answer_until(client, model, rec, "尺寸是否合格")
    model.review_responses.append(_answer())
    rec = _turn(client, wid, "外径正常是 20.00mm，超过 20.05mm 就不行")
    crit = _node(rec, "n4")["evaluation_criteria"]
    assert len(crit) == 1
    assert crit[0]["description"] == "外径正常是 20.00mm，超过 20.05mm 就不行"  # verbatim
    assert crit[0]["unit"] == "mm" and crit[0]["expected"]["target"] == 20.0
    # "超过 20.05mm 就不行" -> a reject band starting just above 20.05.
    assert {"band": "reject", "lower": 20.05, "lower_inclusive": False} in crit[0]["limits"]
    assert any("记下了「尺寸是否合格」的判断标准" in c for c in rec["turns"][-1]["changes"])

    rec = _answer_until(client, model, rec, "工艺工程师签字放行")
    model.review_responses.append(_answer())
    rec = _turn(client, wid, "一般2小时内要签，超时了就找车间主任")
    sla = _node(rec, "n5")["sla_config"]
    assert sla["duration"] == "PT2H" and sla["escalate_to_role"] == "车间主任"
    assert sla["description"] == "一般2小时内要签，超时了就找车间主任"

    # The ontology view picks both up.
    view = client.get(f"/api/expert-workflows/{wid}/ontology").json()
    reg = view["ontology"]
    assert any(c.get("expected", {}).get("target") == 20.0 for c in reg["checks"])
    assert any(t.get("duration") == "PT2H" for t in reg["time_constraints"])
    assert any(lvl["to_role_id"] == "role_车间主任" for p in reg["escalation_policies"] for lvl in p["levels"])

    # Neither question is asked again.
    asked = [t.get("question") or "" for t in rec["turns"] if t["role"] != "expert"]
    assert sum("尺寸是否合格" in q and "具体的标准" in q for q in asked) == 1


def test_declined_answer_records_nothing_and_is_not_asked_again(client, model):
    rec = client.post("/api/expert-workflows", json={}).json()
    rec = _narrate(client, rec["id"])
    wid = rec["id"]
    rec = _answer_until(client, model, rec, "尺寸是否合格")
    model.review_responses.append(_answer())
    rec = _turn(client, wid, "没有具体数值，靠经验看")
    assert not _node(rec, "n4").get("evaluation_criteria")
    for _ in range(8):  # run the rest of the list down
        if rec["stage"] != "review_review":
            break
        model.review_responses.append(_answer())
        rec = _turn(client, wid, "就是这样")
    asked = [t.get("question") or "" for t in rec["turns"] if t["role"] != "expert"]
    assert sum("尺寸是否合格" in q and "具体的标准" in q for q in asked) == 1


def test_unrelated_reply_does_not_write_fields(client, model):
    """A reply the model doesn't read as an answer (e.g. a question back) records nothing."""
    rec = client.post("/api/expert-workflows", json={}).json()
    rec = _narrate(client, rec["id"])
    wid = rec["id"]
    rec = _answer_until(client, model, rec, "工艺工程师签字放行")
    model.review_responses.append({**_answer(), "intent": "other"})
    rec = _turn(client, wid, "你说的超时是指什么？")
    assert not _node(rec, "n5").get("sla_config")


def test_readback_shows_captured_details():
    graph = {**EXTRACTED, "nodes": [
        dict(n, evaluation_criteria=[{"id": "c1", "description": "超过 20.05mm 就不行"}]) if n["node_id"] == "n4"
        else dict(n, sla_config={"type": "deadline", "description": "2小时内要签"}) if n["node_id"] == "n5" else n
        for n in EXTRACTED["nodes"]]}
    body = review_agent.readback(graph)
    assert "判断标准：「超过 20.05mm 就不行」" in body and "时限：「2小时内要签」" in body


def test_ontology_question_is_asked_when_next_even_if_model_prefers_another():
    """With a real model, the model kept preferring its own fresh uncertainties, so the rule-ranked
    threshold / time-limit questions were never reached. When one is next in line, it is asked."""
    state = review_agent.new_state("create")
    state["phase"] = "review"
    state["gaps"] = review_gaps.refresh([], EXTRACTED, mode="create",
                                        new_model_gaps=[review_gaps.model_gap("返工时谁来确认？", ["n6"])])
    # Settle everything ranked above the ontology questions.
    state["gaps"] = [dict(g, status="resolved") if g["priority"] < review_gaps.PRIORITY["criterion"] else g for g in state["gaps"]]
    model_gap = next(g for g in state["gaps"] if g["kind"] == "model")
    result = review_agent._next_question(state, EXTRACTED, review_agent.TurnResult(state=state), (model_gap["id"], "返工时谁来确认？"))
    assert state["pending_gap_id"] == "criterion:n4" and "尺寸是否合格" in result.question
