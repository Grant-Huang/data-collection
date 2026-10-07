"""Head-to-tail connectivity of the workflow DAG ("没头没尾") across the whole conversational
loop: drafting from a narration, editing by conversation, annotation, and the rule-based guide
handing its final review to the review loop.

The model is replaced by scripted responses that reproduce the mistakes local models make in
practice (missing start/end, a branch left unconnected, a step removed without reconnecting,
a step inserted with only one edge, ops listed out of order, rework drawn as a back-edge).
What is checked is the code-side guarantee: such a graph is either repaired where there is
exactly one sensible reading, or reported and kept from being confirmed -- never saved
silently.
"""
import copy
import re

import pytest

from app import graph_ops, graph_validator, llm_client, review_agent

NARRATIVE = ("设备报警以后，操作员先按急停，把零件隔离到待判区，然后叫质量工程师复测。复测正常就恢复生产；"
             "确认超差的话，设备工程师查主轴和夹具，查完换刀，再试切首件，首件合格就恢复生产，这件事就算处理完了。")


def _n(i, t, label, ev=None):
    return {"node_id": i, "node_type": t, "label": label, "actor_roles": [], "evidence": ev or label}


def _e(i, a, b, t="normal", c=None):
    return {"edge_id": i, "from": a, "to": b, "edge_type": t, "condition": c}


# start -> 隔离 -> 复测 -> 判断 -(正常)-> 恢复生产(end)
#                           \-(超差)-> 查主轴 -> 换刀 -> 试切 -> 恢复生产
GOOD = {
    "nodes": [_n("n1", "start", "设备报警", "设备报警以后"), _n("n2", "activity", "按急停并隔离零件", "操作员先按急停"),
              _n("n3", "activity", "质量工程师复测", "叫质量工程师复测"), _n("n4", "decision", "复测结果", "确认超差的话"),
              _n("n5", "activity", "查主轴和夹具", "设备工程师查主轴和夹具"), _n("n6", "activity", "换刀", "查完换刀"),
              _n("n7", "activity", "试切首件", "再试切首件"), _n("n8", "end", "恢复生产", "恢复生产")],
    "edges": [_e("e1", "n1", "n2"), _e("e2", "n2", "n3"), _e("e3", "n3", "n4"),
              _e("e4", "n4", "n8", "conditional", "复测正常"), _e("e5", "n4", "n5", "conditional", "确认超差"),
              _e("e6", "n5", "n6"), _e("e7", "n6", "n7"), _e("e8", "n7", "n8")],
    "start_node_ids": ["n1"], "end_node_ids": ["n8"],
    "summary": "设备报警后停机隔离、复测，超差就查设备换刀试切。", "uncertainties": [], "case_context": {},
}


def _variant(fn):
    g = copy.deepcopy(GOOD)
    fn(g)
    return g


def _without_edge(edge_id):
    return _variant(lambda g: g.__setitem__("edges", [e for e in g["edges"] if e["edge_id"] != edge_id]))


def _graph(raw=GOOD):
    """GOOD as a stored graph (what graph_ops / the validator see)."""
    g = copy.deepcopy({k: raw[k] for k in ("nodes", "edges", "start_node_ids", "end_node_ids")})
    g["graph_type"] = "dag"
    return graph_ops.assign_missing_seqs(g)


def _codes(graph):
    return {i["code"] for i in graph_validator.validate(graph) if i["level"] == "error"}


def _connected_head_to_tail(graph):
    """Every node reachable from a start and able to reach an end."""
    out, inc = {}, {}
    for e in graph["edges"]:
        out.setdefault(e["from"], []).append(e["to"])
        inc.setdefault(e["to"], []).append(e["from"])

    def reach(seeds, adj):
        seen, stack = set(seeds), list(seeds)
        while stack:
            for y in adj.get(stack.pop(), []):
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
        return seen

    ids = {n["node_id"] for n in graph["nodes"]}
    starts = [n["node_id"] for n in graph["nodes"] if n["node_type"] == "start"]
    ends = [n["node_id"] for n in graph["nodes"] if n["node_type"] == "end"]
    return bool(starts and ends) and reach(starts, out) >= ids and reach(ends, inc) >= ids


# --- validator --------------------------------------------------------------------------------

def test_validator_reports_a_branch_that_leads_nowhere():
    g = _graph(_without_edge("e8"))  # 试切首件 -> end missing
    issues = [i for i in graph_validator.validate(g) if i["code"] == "dangling_tail"]
    assert [i["node_id"] for i in issues] == ["n7"]
    assert not graph_validator.is_valid(g)


def test_validator_reports_steps_nothing_leads_into():
    g = _graph(_without_edge("e6"))  # 查主轴 -/-> 换刀
    by_code = {(i["code"], i["node_id"]) for i in graph_validator.validate(g)}
    assert ("dangling_head", "n6") in by_code and ("dangling_tail", "n5") in by_code


def test_validator_accepts_a_connected_graph():
    assert graph_validator.validate(_graph()) == []


# --- drafting from a narration (专家录入: 口述 -> 建图) -----------------------------------------

class Model:
    def __init__(self, extract=GOOD):
        self.extract = extract
        self.queue: list = []

    def __call__(self, cfg, messages, timeout=None):
        if "流程整理模块" in messages[0]["content"]:
            return copy.deepcopy(self.extract)
        return self.queue.pop(0)


@pytest.fixture
def model(monkeypatch):
    fake = Model()
    monkeypatch.setattr(review_agent, "_slot", lambda slot: {"enabled": True, "endpoint": "http://x", "model_name": "m", "api_key": "k"})
    monkeypatch.setattr(llm_client, "chat_completion_json", fake)
    return fake


def _turn(client, wid, text):
    r = client.post(f"/api/expert-workflows/{wid}/turns", json={"text": text})
    assert r.status_code == 200, r.text
    return client.get(f"/api/expert-workflows/{wid}").json()


def _draft(client, model, extract):
    model.extract = extract
    rec = client.post("/api/expert-workflows", json={}).json()
    return _turn(client, rec["id"], NARRATIVE)


def _edit(ops, text="改一下", **extra):
    return {"intent": "edit", "understanding": f"您是说{text}", "ops": ops, "evidence": extra.get("evidence", {}),
            "resolved_gap_ids": [], "question": None, "new_uncertainties": []}


def review_agent_gap_texts(client, wid):
    from app import db
    return [g["text"] for g in db.get(wid)["_review"]["gaps"]]


def test_draft_without_end_gets_one_and_asks_about_it(client, model):
    # Linear story whose model draft has no end node: the last step just stops.
    linear = {**GOOD, "nodes": [GOOD["nodes"][i] for i in (0, 1, 2)],
              "edges": [GOOD["edges"][0], GOOD["edges"][1]], "end_node_ids": []}
    rec = _draft(client, model, linear)
    g = rec["graph"]
    ends = [n for n in g["nodes"] if n["node_type"] == "end"]
    assert len(ends) == 1 and g["end_node_ids"] == [ends[0]["node_id"]]
    assert any(e["from"] == "n3" and e["to"] == ends[0]["node_id"] for e in g["edges"])
    assert graph_validator.is_valid(g) and _connected_head_to_tail(g)
    # The assumption is put to the expert, not silently kept.
    assert any("「质量工程师复测」当成最后一步" in t for t in review_agent_gap_texts(client, rec["id"]))


def test_draft_with_one_bad_edge_keeps_the_rest(client, model):
    rec = _draft(client, model, _variant(lambda g: g["edges"].append(_e("e9", "n7", "n99"))))
    assert len(rec["graph"]["nodes"]) == len(GOOD["nodes"]) and graph_validator.is_valid(rec["graph"])


def test_draft_without_start_gets_one(client, model):
    rec = _draft(client, model, _variant(lambda g: (g["nodes"].pop(0), g["edges"].pop(0), g.__setitem__("start_node_ids", []))))
    g = rec["graph"]
    assert _connected_head_to_tail(g) and g["start_node_ids"] and "missing_start" not in _codes(g)


def test_draft_with_empty_start_id_list_is_synced(client, model):
    rec = _draft(client, model, _variant(lambda g: g.__setitem__("start_node_ids", [])))
    assert rec["graph"]["start_node_ids"] == ["n1"]


def test_draft_with_back_edge_becomes_retry_semantics(client, model):
    rec = _draft(client, model, _variant(lambda g: g["edges"].append(_e("e9", "n7", "n5"))))
    g = rec["graph"]
    assert "cycle_detected" not in _codes(g) and not any(e["from"] == "n7" and e["to"] == "n5" for e in g["edges"])
    n7 = next(n for n in g["nodes"] if n["node_id"] == "n7")
    assert n7["retry_semantics"]["rework_reference_node_id"] == "n5"
    assert any("回到「查主轴和夹具」" in t for t in review_agent_gap_texts(client, rec["id"]))


def test_draft_with_dangling_branch_cannot_be_confirmed_until_fixed(client, model):
    rec = _draft(client, model, _without_edge("e8"))
    wid = rec["id"]
    assert "dangling_tail" in _codes(rec["graph"])
    # The very first question is the structural one, phrased for the expert.
    assert "「试切首件」做完之后接着做哪一步" in rec["turns"][-1]["question"]
    # Satisfied + confirm: refused, and the reply says what's wrong.
    rec = _turn(client, wid, "没问题")
    assert "之后没有接下去" in rec["turns"][-1]["body"]  # visible in the read-back
    rec = _turn(client, wid, "确认")
    assert rec["status"] != "expert_confirmed"
    assert "「试切首件」之后没有接下去" in rec["turns"][-1]["body"]
    # The expert says how it continues; the model adds the edge; now it confirms.
    model.queue.append(_edit([{"op": "add_edge", "edge": _e("x", "n7", "n8")}], "试切合格就恢复生产"))
    rec = _turn(client, wid, "试切合格就恢复生产")
    assert _connected_head_to_tail(rec["graph"])
    _turn(client, wid, "没问题")
    rec = _turn(client, wid, "确认")
    assert rec["status"] == "expert_confirmed"


# --- editing by conversation (专家录入: 对话改图) -----------------------------------------------

def _edited(client, model, ops, text="改一下", evidence=None):
    rec = _draft(client, model, GOOD)
    model.queue.append(_edit(ops, text, evidence=evidence or {}))
    return _turn(client, rec["id"], text)


def test_removing_a_middle_step_reconnects_its_neighbours(client, model):
    rec = _edited(client, model, [{"op": "remove_node", "node_id": "n6"}], "不用换刀")
    g = rec["graph"]
    assert "换刀" not in {n["label"] for n in g["nodes"]} and _connected_head_to_tail(g)
    assert any(e["from"] == "n5" and e["to"] == "n7" for e in g["edges"])
    assert any("「查主轴和夹具」之后改为接「试切首件」" in c for c in rec["turns"][-1]["changes"])


def test_removing_the_first_step_of_a_branch_keeps_its_condition(client, model):
    rec = _edited(client, model, [{"op": "remove_node", "node_id": "n5"}], "不用查主轴")
    edge = next(e for e in rec["graph"]["edges"] if e["from"] == "n4" and e["to"] == "n6")
    assert edge["edge_type"] == "conditional" and edge["condition"] == "确认超差"
    assert _connected_head_to_tail(rec["graph"]) and graph_validator.is_valid(rec["graph"])


def test_inserting_a_step_with_only_its_incoming_edge_is_spliced_in(client, model):
    rec = _edited(client, model, [
        {"op": "add_node", "node": {"node_id": "new1", "node_type": "activity", "label": "通知班组长", "actor_roles": []}},
        {"op": "add_edge", "edge": _e("x", "n5", "new1")}], "查完主轴要通知班组长", {"new1": "通知班组长"})
    g = rec["graph"]
    new = next(n["node_id"] for n in g["nodes"] if n["label"] == "通知班组长")
    assert {(e["from"], e["to"]) for e in g["edges"]} >= {("n5", new), (new, "n6")}
    assert not any(e["from"] == "n5" and e["to"] == "n6" for e in g["edges"])
    changes = rec["turns"][-1]["changes"]
    assert any("新增步骤「通知班组长」（接在「查主轴和夹具」之后，然后接「换刀」）" in c for c in changes)
    assert not any(c.startswith("去掉了") for c in changes)  # an insertion, not a cut


def test_inserting_a_step_with_only_its_outgoing_edge_is_spliced_in(client, model):
    rec = _edited(client, model, [
        {"op": "add_node", "node": {"node_id": "new1", "node_type": "activity", "label": "通知班组长", "actor_roles": []}},
        {"op": "add_edge", "edge": _e("x", "new1", "n6")}], "换刀前要通知班组长", {"new1": "通知班组长"})
    assert _connected_head_to_tail(rec["graph"])


def test_appending_a_last_step_moves_the_end_after_it(client, model):
    rec = _edited(client, model, [
        {"op": "add_node", "node": {"node_id": "new1", "node_type": "activity", "label": "班组长签字放行", "actor_roles": []}},
        {"op": "add_edge", "edge": _e("x", "n7", "new1")}], "试切完还要班组长签字放行", {"new1": "班组长签字放行"})
    g = rec["graph"]
    new = next(n["node_id"] for n in g["nodes"] if n["label"] == "班组长签字放行")
    assert any(e["from"] == new and e["to"] == "n8" for e in g["edges"]) and _connected_head_to_tail(g)


def test_ops_order_does_not_matter(client, model):
    rec = _edited(client, model, [
        {"op": "add_edge", "edge": _e("x", "n5", "new1")},
        {"op": "add_edge", "edge": _e("y", "new1", "n6")},
        {"op": "remove_edge", "edge_id": "e6"},
        {"op": "add_node", "node": {"node_id": "new1", "node_type": "activity", "label": "通知班组长", "actor_roles": []}}],
        "查完主轴要通知班组长", {"new1": "通知班组长"})
    assert "通知班组长" in {n["label"] for n in rec["graph"]["nodes"]} and _connected_head_to_tail(rec["graph"])


def test_retyping_the_end_keeps_end_ids_in_sync(client, model):
    rec = _edited(client, model, [
        {"op": "update_node", "node_id": "n8", "patch": {"node_type": "activity"}},
        {"op": "add_node", "node": {"node_id": "new1", "node_type": "end", "label": "写完报告", "actor_roles": []}},
        {"op": "add_edge", "edge": _e("x", "n8", "new1")}], "恢复生产后写完报告才算完")
    g = rec["graph"]
    assert g["end_node_ids"] == [n["node_id"] for n in g["nodes"] if n["node_type"] == "end"]
    assert len(g["end_node_ids"]) == 1 and _connected_head_to_tail(g)


def test_removing_a_whole_branch_drops_the_decision(client, model):
    rec = _edited(client, model, [{"op": "remove_node", "node_id": i} for i in ("n5", "n6", "n7")], "超差那条路不用管")
    g = rec["graph"]
    assert "decision" not in {n["node_type"] for n in g["nodes"]}
    assert any(e["from"] == "n3" and e["to"] == "n8" for e in g["edges"]) and _connected_head_to_tail(g)


def test_edit_that_cannot_be_completed_is_still_refused(client, model):
    rec = _draft(client, model, GOOD)
    before = rec["graph"]
    model.queue.append(_edit([{"op": "remove_node", "node_id": "n8"}], "试切首件就结束了"))
    rec = _turn(client, rec["id"], "试切首件就结束了")
    assert rec["graph"] == before and "没有改图" in rec["turns"][-1]["body"]


# --- annotation (专家流程标定) -------------------------------------------------------------------

def test_annotation_edit_removing_a_step_stays_connected(client, model):
    from tests.test_annotation_review import SAMPLE, _say, _start
    payload = {"dataset_meta": {**SAMPLE["dataset_meta"], "source_type": "public_extracted"},
               "records": [{**copy.deepcopy(SAMPLE["records"][0]), "provenance": {"source_type": "public_extracted"}}]}
    res = client.post("/api/datasets/import/confirm", json={"payload": payload, "import_records_without_errors": True})
    vid, rid = res.json()["id"], SAMPLE["records"][0]["record_id"]
    s = _start(client, vid, rid, "alice")
    # 试产并首件检验 (n9) removed without reconnecting 汇总分析结果 (n8) -> 恢复生产 (n10).
    model.queue.append({**_edit([{"op": "remove_node", "node_id": "n9"}], "不用试产"), "reason_tags": ["extra_step"]})
    s = _say(client, vid, s["session_id"], "不用试产这一步")
    assert _connected_head_to_tail(s["graph"]) and graph_validator.is_valid(s["graph"])
    s = _say(client, vid, s["session_id"], "确认")
    assert s["status"] == "submitted"


def test_rejecting_a_structurally_broken_record_can_still_be_submitted():
    broken = _graph(_without_edge("e8"))
    state = review_agent.new_state("annotate", base_graph=copy.deepcopy(broken))
    state = review_agent.opening(state, broken).state
    result = review_agent.handle_turn(state, broken, [{"role": "expert", "text": "这条不能用"}], "这条不能用", "t1")
    assert result.state["proposal"]["verdict"] == "rejected"
    result = review_agent.handle_turn(result.state, broken, [{"role": "expert", "text": "确认"}], "确认", "t2")
    assert result.finished


# --- rule-based guide's final review -> conversational editing --------------------------------

def _rule_guide_to_review(client):
    rec = client.post("/api/expert-workflows", json={}).json()
    wid = rec["id"]
    for text in ["设备/质量异常", "3号机尺寸超差报警", "先跳过，直接讲怎么做的", "无", "操作员按急停",
                 "质检员复测", "换刀", "后面就处理完了", "恢复生产", "没有，一直是这么处理",
                 "没有，都是一件做完再做下一件", "没有需要等人确认的", "没有返工的情况", "没有特别靠经验的地方",
                 "就是一个任务"]:
        rec = _turn(client, wid, text)
        if rec["stage"] == "review":
            break
    assert rec["stage"] == "review", rec["stage"]
    return rec


def test_rule_guide_review_without_model_does_not_promise_edits(client):
    rec = _rule_guide_to_review(client)
    rec = _turn(client, rec["id"], "第二步其实是班长做的")
    assert "没法按对话内容改图" in rec["turns"][-1]["text"]


def test_rule_guide_review_hands_off_to_review_loop_when_model_configured(client, monkeypatch):
    rec = _rule_guide_to_review(client)
    by_label = {n["label"]: n["node_id"] for n in rec["graph"]["nodes"]}
    fake = Model()
    fake.queue.append(_edit([{"op": "remove_node", "node_id": by_label["质检员复测"]}], "不用复测"))
    monkeypatch.setattr(review_agent, "_slot", lambda slot: {"enabled": True, "endpoint": "http://x", "model_name": "m", "api_key": "k"})
    monkeypatch.setattr(llm_client, "chat_completion_json", fake)
    rec = _turn(client, rec["id"], "不用复测这一步")
    assert rec["stage"].startswith("review_")
    assert "质检员复测" not in {n["label"] for n in rec["graph"]["nodes"]}
    assert _connected_head_to_tail(rec["graph"])
    # Steps came verbatim from the expert: no "我没找到原话" false alarms after the handoff.
    assert "原话" not in (rec["turns"][-1].get("question") or "")
    # Nothing left to clarify -> straight to the read-back, where "确认" commits.
    assert rec["stage"] == "review_final_confirm"
    rec = _turn(client, rec["id"], "确认")
    assert rec["status"] == "expert_confirmed"


# --- end-to-end findings (narration -> DAG -> restated by a second model from the DAG alone) --

def test_trigger_is_carried_onto_a_generic_start_label(client, model):
    raw = _variant(lambda g: (g["nodes"][0].__setitem__("label", "开始"),
                              g.__setitem__("case_context", {"scenario_trigger": "3号加工中心报警、尺寸超差"})))
    rec = _draft(client, model, raw)
    start = next(n for n in rec["graph"]["nodes"] if n["node_type"] == "start")
    assert start["label"] == "3号加工中心报警、尺寸超差"


def test_specific_start_label_is_kept(client, model):
    raw = _variant(lambda g: g.__setitem__("case_context", {"scenario_trigger": "夜班报警"}))
    rec = _draft(client, model, raw)
    assert next(n for n in rec["graph"]["nodes"] if n["node_type"] == "start")["label"] == "设备报警"


def test_experience_notes_are_kept(client, model):
    rec = _draft(client, model, _variant(lambda g: g.__setitem__(
        "case_context", {"experience_notes": "判断刀具还是夹具靠听声音和看切屑"})))
    assert rec["case_context"]["experience_notes"] == "判断刀具还是夹具靠听声音和看切屑"


def test_structural_nodes_are_not_asked_about_as_unverified(client, model):
    def add_join(g):
        g["nodes"].append({"node_id": "j", "node_type": "merge", "label": "处理完成汇合", "actor_roles": []})
        g["edges"] = [e for e in g["edges"] if e["to"] != "n8"] + [
            _e("a", "n4", "j", "conditional", "复测正常"), _e("b", "n7", "j", "merge"), _e("c", "j", "n8")]
    rec = _draft(client, model, _variant(add_join))
    assert not any("处理完成汇合" in t for t in review_agent_gap_texts(client, rec["id"]))


def test_readback_reads_each_branch_through():
    lines = review_agent.readback(_graph()).splitlines()
    labels = [re.sub(r"^\[\d+\](【[^】]*】)?", "", line).split("：")[0].split("（")[0].split("；")[0] for line in lines]
    # The "超差" branch is read start to finish before anything else follows.
    i = labels.index("查主轴和夹具")
    assert labels[i:i + 3] == ["查主轴和夹具", "换刀", "试切首件"]


def test_both_dag_prompts_carry_the_label_rules():
    from app import guide_service
    assert guide_service.DAG_LABEL_RULES in review_agent._EXTRACT_PROMPT
    assert guide_service.DAG_LABEL_RULES in guide_service._REGENERATE_SYSTEM_PROMPT


def test_label_rules_do_not_fold_approvals_into_ends_or_call_exclusive_merges_complete():
    """Two rule wordings from the first end-to-end round that the second round showed backfiring:
    an approval used as the example of an end label (the model then dropped the approval node),
    and "××都完成" applied to exclusive merges (reads as if every branch happened)."""
    from app import guide_service
    rules = guide_service.DAG_LABEL_RULES
    assert "不要直接当成 end" in rules
    assert "merge" in rules and "不要写\"都完成\"" in rules
