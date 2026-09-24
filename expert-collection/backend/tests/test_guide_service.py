"""Regression tests for the expert-collection interview engine (guide_service planner +
guide_phrasing phraser + router wiring). All run on the rule-based path (no LLM configured)
unless a test patches the LLM layer explicitly."""
from app import graph_validator, guide_phrasing, guide_service
from app.guide_service import (
    END_CHIP, NO_PARALLEL_CHIP, REJOIN_END_CHIP,
)


def _turn(client, wid, text):
    r = client.post(f"/api/expert-workflows/{wid}/turns", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


def _record(client, wid):
    return client.get(f"/api/expert-workflows/{wid}").json()


def _through_background(client, wid):
    _turn(client, wid, "设备/质量异常")
    _turn(client, wid, "CNC 加工件尺寸超差，质检抽检发现的")
    _turn(client, wid, guide_service.GOAL_SKIP_CHIP)
    return _turn(client, wid, "无")


def test_full_conversation_reaches_valid_confirmable_graph(client):
    wid = client.post("/api/expert-workflows", json={}).json()["id"]
    r = _through_background(client, wid)
    assert "第一件事" in r["next_question"]["question"]
    assert r["next_question"]["chips"] is None  # P0 recall question: no chips (PRD 18.2)

    # Main path: more than two steps are collected (the old Wizard stopped after two).
    r = _turn(client, wid, "班组长先停机")
    assert r["next_question"]["question"] == "「班组长先停机」之后，下一步是谁做什么？"
    assert r["next_question"]["ack"].startswith("记下了")
    r = _turn(client, wid, "质检员复测尺寸，如果尺寸超差就要返工")
    r = _turn(client, wid, "工艺员调整刀补")
    r = _turn(client, wid, "操作工试切首件")
    assert r["next_question"]["chips"] == [END_CHIP]
    r = _turn(client, wid, END_CHIP)
    assert "处理完" in r["next_question"]["question"]

    # End condition -> sweeps start. The branch sweep quotes the cue the expert gave earlier.
    r = _turn(client, wid, "首件合格恢复批量生产")
    nq = r["next_question"]
    assert nq["target"] == "branch_discovery"
    assert "你前面提到「如果尺寸超差就要返工」" in nq["question"]
    assert "工艺员调整刀补" in nq["chips"]

    # Branch after "调整刀补": condition A keeps the existing path, condition B is new.
    r = _turn(client, wid, "工艺员调整刀补")
    assert "什么情况下会接着做「操作工试切首件」" in r["next_question"]["question"]
    r = _turn(client, wid, "偏差在刀补范围内")
    r = _turn(client, wid, "偏差太大，换刀后重新对刀")
    assert r["next_question"]["target"] == "branch_rejoin"
    assert "操作工试切首件" in r["next_question"]["chips"]
    r = _turn(client, wid, "操作工试切首件")

    # Parallel sweep: pair chips come from the expert's own consecutive steps.
    assert r["next_question"]["target"] == "parallel_discovery"
    assert r["next_question"]["chips"][-1] == NO_PARALLEL_CHIP
    r = _turn(client, wid, NO_PARALLEL_CHIP)

    # Approval sweep: structure first (chips), then who (open question, PRD 18.3).
    assert r["next_question"]["target"] == "approval_discovery"
    r = _turn(client, wid, "操作工试切首件")
    assert r["next_question"]["target"] == "approval_who"
    assert r["next_question"]["chips"] is None
    r = _turn(client, wid, "质量主管")

    # Retry sweep resolves the rework target to a concrete node.
    assert r["next_question"]["target"] == "retry_discovery"
    r = _turn(client, wid, "操作工试切首件")
    assert r["next_question"]["target"] == "retry_target"
    r = _turn(client, wid, "工艺员调整刀补")

    assert r["next_question"]["target"] == "experience_discovery"
    r = _turn(client, wid, "刀具磨损到什么程度该换，主要靠听声音判断")
    assert r["next_question"] is None
    assert r["completion"]["ready_for_confirmation"] is True
    assert r["completion"]["score"] == 1.0

    rec = _record(client, wid)
    graph = rec["graph"]
    assert graph_validator.is_valid(graph), graph_validator.validate(graph)
    types = [n["node_type"] for n in graph["nodes"]]
    assert types.count("decision") == 1 and types.count("approval") == 1
    approval = next(n for n in graph["nodes"] if n["node_type"] == "approval")
    assert approval["label"] == "审批（质量主管）"
    retry_node = next(n for n in graph["nodes"] if n.get("retry_semantics"))
    target = next(n for n in graph["nodes"] if n["node_id"] == retry_node["retry_semantics"]["rework_reference_node_id"])
    assert target["label"] == "工艺员调整刀补"
    assert rec["case_context"]["experience_notes"].startswith("刀具磨损")

    # Assistant turns carry the layered bubble fields.
    last_q = [t for t in rec["turns"] if t["role"] == "assistant" and t.get("chips")][-1]
    assert last_q["question"] and last_q["why"]

    assert client.post(f"/api/expert-workflows/{wid}/confirm").status_code == 200


def test_ambiguous_connector_and_negated_simultaneous(client):
    wid = client.post("/api/expert-workflows", json={}).json()["id"]
    _through_background(client, wid)
    r = _turn(client, wid, "记录系统并通知班组长")
    assert r["next_question"]["target"] == "parallel_merge_discovery"
    r = _turn(client, wid, "不是同时做的，先记录")
    graph = r["current_dag"]
    # "不是同时" must NOT be read as parallel.
    assert not any(n["node_type"] == "parallel_split" for n in graph["nodes"])
    assert [n["label"] for n in graph["nodes"] if n["node_type"] == "activity"] == ["记录系统", "通知班组长"]


def test_parallel_sweep_rewires_consecutive_steps(client):
    wid = client.post("/api/expert-workflows", json={}).json()["id"]
    _through_background(client, wid)
    for step in ["停机", "检查设备", "检查工艺参数", "恢复生产"]:
        _turn(client, wid, step)
    _turn(client, wid, END_CHIP)
    _turn(client, wid, "产线恢复")
    r = _turn(client, wid, "没有，一直是这么处理")
    assert r["next_question"]["target"] == "parallel_discovery"
    r = _turn(client, wid, "「检查设备」和「检查工艺参数」")
    graph = r["current_dag"]
    assert graph_validator.is_valid(graph), graph_validator.validate(graph)
    assert sum(n["node_type"] == "parallel_split" for n in graph["nodes"]) == 1


def test_background_is_short_and_skippable(client):
    wid = client.post("/api/expert-workflows", json={}).json()["id"]
    # Expert jumps straight into the story on the opening question.
    r = _turn(client, wid, "上周三夜班 CNC 主轴突然报警停机，操作工叫我过去看")
    assert r["next_question"]["chips"] == [guide_service.GOAL_SKIP_CHIP]
    r = _turn(client, wid, guide_service.GOAL_SKIP_CHIP)
    assert r["next_question"]["chip_mode"] == "multi_select"
    r = _turn(client, wid, "时间紧、缺备件/物料")
    # Several picks -> one merged question, never several questions glued with "；".
    q = r["next_question"]["question"]
    assert "；" not in q and q.count("？") == 1
    r = _turn(client, wid, "要两小时内恢复，主轴轴承没库存")
    assert "第一件事" in r["next_question"]["question"]
    rec = _record(client, wid)
    assert rec["case_context"]["scenario_trigger"].startswith("上周三")
    assert "scenario_goal" in rec["case_context"]["skipped_fields"]


def test_rollback_restores_snapshot_after_sweep_rewire(client, monkeypatch):
    wid = client.post("/api/expert-workflows", json={}).json()["id"]
    _through_background(client, wid)
    for step in ["停机", "复测尺寸", "恢复生产"]:
        _turn(client, wid, step)
    _turn(client, wid, END_CHIP)
    _turn(client, wid, "产线恢复")
    before_branch = _record(client, wid)["graph"]
    _turn(client, wid, "复测尺寸")          # decision inserted, existing edge rewired
    _turn(client, wid, "尺寸合格")
    _turn(client, wid, "尺寸超差")          # condition only -> branch_b_steps (a step stage)

    real = guide_service._understand_step_and_check_correction
    monkeypatch.setattr(guide_service, "_understand_step_and_check_correction",
                        lambda text: {**real(text), "is_correction": True})
    r = _turn(client, wid, "哦我说错了")
    chips = r["next_question"]["chips"]
    assert chips[-1] == "不是，这是新的一步"
    pick = next(c for c in chips if "复测尺寸" in c)
    _turn(client, wid, pick)
    graph = _record(client, wid)["graph"]
    # Restored exactly: no half-rewired decision left behind, still a valid graph.
    assert graph == before_branch
    assert graph_validator.is_valid(graph)


def test_legacy_structural_stage_is_migrated():
    graph = {"graph_type": "dag", "start_node_ids": ["s"], "end_node_ids": [],
             "nodes": [{"node_id": "s", "node_type": "start", "label": "开始"},
                       {"node_id": "a", "node_type": "activity", "label": "停机"}],
             "edges": [{"edge_id": "e", "from": "s", "to": "a", "edge_type": "normal"}]}
    reply, ops, nq, state = guide_service.handle_turn(
        {"stage": "branch_check", "cursor": "a", "pending": {}}, "只有一种处理方式", graph=graph)
    assert state["stage"] == "end_condition" and state["cursor"] == "a"
    assert nq["target"] == "end_condition_discovery"


# --- Phrasing layer -------------------------------------------------------------------------

def _validate(ack, question, template="「停机」之后，下一步是谁做什么？", editable=True,
              corpus="班组长先停机\n停机"):
    return guide_phrasing._validate(ack, question, template_question=template,
                                    question_editable=editable, corpus=corpus)


def test_phrasing_validation_rules():
    assert _validate("停机这步记下了。", "「停机」之后，接下来谁做了什么？")
    assert not _validate("「质检员」停机了。", "「停机」之后呢？")         # invented quote
    assert not _validate("停机 30 分钟。", "「停机」之后呢？")             # invented number
    assert not _validate("记下了。", "「停机」之后是哪个分支？")            # jargon
    assert not _validate("记下了。", "之后做什么？谁做的？")                # two questions + lost anchor
    assert not _validate("记下了。", "接下来做什么？")                      # anchor quote dropped
    assert not _validate("停机了吗？", "「停机」之后呢？")                  # ack must not ask


def test_finalize_uses_valid_llm_output_and_falls_back_on_invalid(monkeypatch):
    monkeypatch.setattr(guide_phrasing.app_settings, "resolve_slot_for_call",
                        lambda settings, slot: {"enabled": True, "endpoint": "http://x", "model_name": "m"})
    nq = {"target": "main_path_discovery", "priority": "P0", "question": "「停机」之后，下一步是谁做什么？", "chips": None}

    monkeypatch.setattr(guide_phrasing, "_llm_polish", lambda *a, **k: ("先停机，这个处理很及时。", "「停机」之后，接下来是谁做了什么？"))
    reply, out = guide_phrasing.finalize("记下了：「停机」。", nq, last_expert_message="班组长先停机")
    assert out["ack"] == "先停机，这个处理很及时。"
    assert out["question"] == "「停机」之后，接下来是谁做了什么？"
    assert out["why"]

    monkeypatch.setattr(guide_phrasing, "_llm_polish", lambda *a, **k: ("质检员 5 分钟后到场。", "然后呢？"))
    reply, out = guide_phrasing.finalize("记下了：「停机」。", nq, last_expert_message="班组长先停机")
    assert out["ack"] == "记下了：「停机」。" and out["question"] == nq["question"]

    # Chip questions are never reworded, even if the model returns a valid-looking rewrite.
    chip_nq = {**nq, "chips": ["后面就处理完了"]}
    monkeypatch.setattr(guide_phrasing, "_llm_polish", lambda *a, **k: ("停机记下了。", "「停机」之后还有别的事吗？"))
    reply, out = guide_phrasing.finalize("记下了：「停机」。", chip_nq, last_expert_message="班组长先停机")
    assert out["question"] == nq["question"] and out["ack"] == "停机记下了。"

    # ...except when the only chip is a generic "done" fallback the planner marked rephrasable.
    fallback_nq = {**chip_nq, "rephrasable": True}
    reply, out = guide_phrasing.finalize("记下了：「停机」。", fallback_nq, last_expert_message="班组长先停机")
    assert out["question"] == "「停机」之后还有别的事吗？" and "rephrasable" not in out


# --- 「刷新工作流图」 resets conversation progress --------------------------------------------

def _regenerated_graph():
    nodes = [
        {"node_id": "s", "node_type": "start", "label": "开始"},
        {"node_id": "a", "node_type": "activity", "label": "停机检查"},
        {"node_id": "b", "node_type": "activity", "label": "更换刀具"},
        {"node_id": "e", "node_type": "end", "label": "恢复生产"},
    ]
    edges = [
        {"edge_id": "e1", "from": "s", "to": "a", "edge_type": "normal"},
        {"edge_id": "e2", "from": "a", "to": "b", "edge_type": "normal"},
        {"edge_id": "e3", "from": "b", "to": "e", "edge_type": "normal"},
    ]
    for n in nodes:
        n.update({"actor_roles": [], "decision_question": None, "confidence": 0.6,
                  "expert_confirmed": False, "source_turn_ids": []})
    for e in edges:
        e.update({"condition": None, "confidence": 0.6, "expert_confirmed": False, "source_turn_ids": []})
    return {"graph_type": "dag", "start_node_ids": ["s"], "end_node_ids": ["e"], "nodes": nodes, "edges": edges}


def test_regenerate_resets_progress_mid_main_path(client, monkeypatch):
    wid = client.post("/api/expert-workflows", json={}).json()["id"]
    _through_background(client, wid)
    _turn(client, wid, "班组长先停机")
    _turn(client, wid, "质检员复测尺寸")          # stage main_path, cursor on an old node id
    monkeypatch.setattr(guide_service, "regenerate_graph_from_transcript", lambda turns: _regenerated_graph())

    r = client.post(f"/api/expert-workflows/{wid}/regenerate-graph")
    assert r.status_code == 200, r.text
    rec = r.json()
    nq = rec["unresolved"][0]
    # Continues from the structural sweeps, with chips rebuilt from the *new* graph's steps.
    assert rec["stage"] == "sweep_branch_pick" and nq["target"] == "branch_discovery"
    assert "停机检查" in nq["chips"] and "班组长先停机" not in nq["chips"]
    assert rec["turns"][-1]["role"] == "assistant" and "重新整理" in rec["turns"][-1]["ack"]
    assert rec["status"] == "collecting" and rec["completion"]["ready_for_confirmation"] is False

    # Answering a sweep acts on the new graph and keeps it valid.
    r = _turn(client, wid, "停机检查")
    assert "什么情况下会接着做「更换刀具」" in r["next_question"]["question"]
    assert graph_validator.is_valid(r["current_dag"]) is False  # decision waits for its 2nd branch
    _turn(client, wid, "刀具磨损")
    r = _turn(client, wid, "刀具正常，调整参数")
    assert r["next_question"]["target"] == "branch_rejoin"


def test_regenerate_skips_answered_sweeps_and_clears_rollback_log(client, monkeypatch):
    wid = client.post("/api/expert-workflows", json={}).json()["id"]
    _through_background(client, wid)
    for step in ["停机", "复测尺寸"]:
        _turn(client, wid, step)
    _turn(client, wid, END_CHIP)
    _turn(client, wid, "产线恢复")
    _turn(client, wid, "没有，一直是这么处理")         # branch sweep answered
    _turn(client, wid, NO_PARALLEL_CHIP)                # parallel sweep answered
    monkeypatch.setattr(guide_service, "regenerate_graph_from_transcript", lambda turns: _regenerated_graph())

    rec = client.post(f"/api/expert-workflows/{wid}/regenerate-graph").json()
    assert rec["unresolved"][0]["target"] == "approval_discovery"   # branch/parallel not repeated
    from app import db
    assert db.get(wid)["_turn_state_log"] == []

    # Finish the remaining sweeps -> final review, confirmable.
    _turn(client, wid, "没有需要等人确认的")
    _turn(client, wid, "没有返工的情况")
    r = _turn(client, wid, "没有特别靠经验的地方")
    assert r["next_question"] is None and r["completion"]["ready_for_confirmation"] is True
