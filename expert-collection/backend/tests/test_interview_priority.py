"""Narrate-first interview: telling the story in several pieces, and asking the clarification
list strictly by severity without drifting into a tangent around one step.

The model is replaced by scripted responses (same approach as test_review_loop.py) -- this
checks the code-side rules, not model quality."""
import pytest

from app import llm_client, review_agent, review_gaps

PART_1 = "设备报警以后，操作员先按急停，把这批零件隔离到待判区，然后叫质量工程师来复测。"
PART_2 = "复测正常就恢复生产；确认超差的话，设备工程师查主轴和夹具，查完换刀试切首件，首件合格就恢复生产。"

# A draft with one decision (conditions filled), no approval / retry / parallel steps, and one
# step without an actor -- so the rule list holds coverage (structure) and actor (detail) items.
EXTRACTED = {
    "nodes": [
        {"node_id": "n1", "node_type": "start", "label": "设备报警", "actor_roles": [], "evidence": "设备报警以后"},
        {"node_id": "n2", "node_type": "activity", "label": "按急停并隔离零件", "actor_roles": ["操作员"], "evidence": "操作员先按急停"},
        {"node_id": "n3", "node_type": "activity", "label": "复测", "actor_roles": [], "evidence": "叫质量工程师来复测"},
        {"node_id": "n4", "node_type": "decision", "label": "是否超差", "actor_roles": [], "evidence": "确认超差的话"},
        {"node_id": "n5", "node_type": "activity", "label": "检查主轴和夹具", "actor_roles": ["设备工程师"], "evidence": "设备工程师查主轴和夹具"},
        {"node_id": "n7", "node_type": "end", "label": "恢复生产", "actor_roles": [], "evidence": "恢复生产"},
    ],
    "edges": [
        {"edge_id": "e1", "from": "n1", "to": "n2", "edge_type": "normal"},
        {"edge_id": "e2", "from": "n2", "to": "n3", "edge_type": "normal"},
        {"edge_id": "e3", "from": "n3", "to": "n4", "edge_type": "normal"},
        {"edge_id": "e4", "from": "n4", "to": "n7", "edge_type": "conditional", "condition": "复测正常"},
        {"edge_id": "e5", "from": "n4", "to": "n5", "edge_type": "conditional", "condition": "确认超差"},
        {"edge_id": "e6", "from": "n5", "to": "n7", "edge_type": "normal"},
    ],
    "start_node_ids": ["n1"], "end_node_ids": ["n7"],
    "summary": "设备报警后停机隔离，复测后按结果恢复生产或查设备。",
    # Six doubts from the first draft: only MAX_MODEL_GAPS of them may enter the list.
    "uncertainties": [{"question": f"第{i}个疑问是什么？", "node_ids": []} for i in range(6)],
    "case_context": {},
}


class FakeModel:
    def __init__(self):
        self.review_responses: list = []
        self.extract_inputs: list[str] = []

    def __call__(self, cfg, messages, timeout=None):
        if "流程整理模块" in messages[0]["content"]:
            self.extract_inputs.append(messages[-1]["content"])
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


def _reply(question=None, new_uncertainties=(), intent="answer"):
    return {"intent": intent, "understanding": "明白。", "ops": [], "evidence": {}, "resolved_gap_ids": [],
            "question": question, "new_uncertainties": list(new_uncertainties)}


# --- telling the story in several pieces ----------------------------------------------------

def test_story_in_pieces_is_extracted_once_when_expert_says_done(client, model):
    wid = client.post("/api/expert-workflows", json={}).json()["id"]

    rec = _turn(client, wid, PART_1)
    assert rec["stage"] == "review_narrative" and model.extract_inputs == []
    rec = _turn(client, wid, PART_2)
    assert rec["stage"] == "review_narrative" and model.extract_inputs == []
    assert "讲完了" in rec["turns"][-1]["body"]

    rec = _turn(client, wid, "讲完了")
    assert rec["stage"] == "review_review" and len(model.extract_inputs) == 1
    # Both pieces reach the extractor; the "讲完了" signal itself is not part of the story.
    sent = model.extract_inputs[0]
    assert PART_1 in sent and PART_2 in sent and "讲完了" not in sent


def test_done_with_too_little_story_asks_for_more(client, model):
    wid = client.post("/api/expert-workflows", json={}).json()["id"]
    _turn(client, wid, "设备报警了")
    rec = _turn(client, wid, "讲完了")
    assert rec["stage"] == "review_narrative" and model.extract_inputs == []
    assert "再多讲一些" in rec["turns"][-1]["body"]


def test_done_signal_only_counts_for_short_messages():
    assert review_agent.is_narrative_done("讲完了")
    assert review_agent.is_narrative_done("我说完了。")
    assert review_agent.is_narrative_done("重试")
    # A narration that merely contains the words is still narration.
    assert not review_agent.is_narrative_done("等质量工程师讲完了以后，我们再决定要不要停线。")


# --- strict severity order ---------------------------------------------------------------------

def test_tiers_rank_fatal_then_structure_then_detail_then_model():
    gaps = review_gaps.refresh([], EXTRACTED, mode="create",
                               new_model_gaps=[review_gaps.model_gap("首件是谁确认的？", ["n5"])])
    order = [review_gaps.tier(g) for g in review_gaps.open_gaps(gaps)]
    assert order == sorted(order, key=["fatal", "structure", "detail", "model"].index)
    kinds = [g["id"] for g in review_gaps.open_gaps(gaps)]
    # Exceptions / approval / rework existence come before who-does-what and before experience.
    assert kinds.index("coverage:approval") < kinds.index("missing_actor:all") < kinds.index("coverage:experience")


def test_most_severe_item_is_asked_even_if_model_prefers_another():
    state = review_agent.new_state("create")
    state["phase"] = "review"
    state["gaps"] = review_gaps.refresh([], EXTRACTED, mode="create",
                                        new_model_gaps=[review_gaps.model_gap("首件是谁确认的？", ["n5"])])
    model_gap = next(g for g in state["gaps"] if g["kind"] == "model")
    top = review_gaps.open_gaps(state["gaps"])[0]
    result = review_agent._next_question(state, EXTRACTED, review_agent.TurnResult(state=state),
                                         (model_gap["id"], "首件是谁确认的？"))
    assert state["pending_gap_id"] == top["id"] != model_gap["id"]
    assert result.question == top["text"]


def test_model_wording_is_used_for_the_top_item():
    state = review_agent.new_state("create")
    state["phase"] = "review"
    state["gaps"] = review_gaps.refresh([], EXTRACTED, mode="create")
    top = review_gaps.open_gaps(state["gaps"])[0]
    result = review_agent._next_question(state, EXTRACTED, review_agent.TurnResult(state=state),
                                         (top["id"], "换个说法问一下"))
    assert result.question == "换个说法问一下"


# --- no drifting -----------------------------------------------------------------------------

def test_first_draft_doubts_are_capped(client, model):
    wid = client.post("/api/expert-workflows", json={}).json()["id"]
    _turn(client, wid, PART_1 + PART_2)
    _turn(client, wid, "讲完了")
    from app import db
    gaps = db.get(wid)["_review"]["gaps"]
    assert sum(1 for g in gaps if g["kind"] == "model") == review_gaps.MAX_MODEL_GAPS


def test_no_follow_up_doubt_about_the_step_just_answered():
    answered = {"id": "missing_actor:all", "source": "rule", "node_ids": ["n3"]}
    same_step = review_gaps.model_gap("复测用的是哪台仪器？", ["n3"])
    other_step = review_gaps.model_gap("隔离区满了怎么办？", ["n2"])
    admitted = review_gaps.admit_model_gaps([], [same_step, other_step], answered=answered)
    assert admitted == [other_step]


def test_a_follow_up_never_spawns_another_follow_up():
    answered = review_gaps.model_gap("首件是谁确认的？", ["n5"])
    admitted = review_gaps.admit_model_gaps([answered], [review_gaps.model_gap("班长不在怎么办？", [])], answered=answered)
    assert admitted == []


def test_model_doubts_total_is_capped():
    existing = [review_gaps.model_gap(f"疑问{i}？", []) for i in range(review_gaps.MAX_MODEL_GAPS)]
    assert review_gaps.admit_model_gaps(existing, [review_gaps.model_gap("再一个？", [])], answered=None) == []


def test_answering_a_question_keeps_the_interview_on_completeness(client, model):
    """End to end: the model keeps raising a doubt on the step just answered -- it is dropped,
    and the next question is the next most severe completeness item, not a tangent."""
    wid = client.post("/api/expert-workflows", json={}).json()["id"]
    _turn(client, wid, PART_1 + PART_2)
    rec = _turn(client, wid, "讲完了")
    from app import db
    first = db.get(wid)["_review"]["pending_gap_id"]
    first_gap = next(g for g in db.get(wid)["_review"]["gaps"] if g["id"] == first)
    assert review_gaps.tier(first_gap) in ("fatal", "structure")

    model.review_responses.append(_reply(new_uncertainties=[{"question": "那一步具体怎么做的？", "node_ids": first_gap["node_ids"] or ["n4"]}]))
    _turn(client, wid, "没有例外，都是这么处理")
    state = db.get(wid)["_review"]
    nxt = next(g for g in state["gaps"] if g["id"] == state["pending_gap_id"])
    assert nxt["kind"] != "model"
