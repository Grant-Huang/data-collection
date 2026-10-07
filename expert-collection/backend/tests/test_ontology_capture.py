"""Ontology follow-up questions in the interview (step 4 of the ontology plan): parsing the
expert's "靠什么判断" / "最晚多久" answers, and the criterion / timing sweeps themselves."""
import pytest

from app import guide_service
from app.guide_service import END_CHIP, NO_PARALLEL_CHIP
from app.ontology_capture import criterion_from_answer, parse_criterion_answer, parse_duration, sla_from_answer


@pytest.mark.parametrize("text,limits,expected,unit", [
    ("温度在15到35度之间，正常25度左右，超过40度就得停",
     [{"band": "normal", "lower": 15.0, "upper": 35.0}, {"band": "reject", "lower": 40.0, "lower_inclusive": False}],
     {"target": 25.0}, "度"),
    ("CPK 不低于 1.33", [{"band": "normal", "lower": 1.33}], None, None),
    ("刀具寿命 > 50%", [{"band": "normal", "lower": 50.0, "lower_inclusive": False}], None, "%"),
    ("偏差不能超过0.02mm", [{"band": "normal", "upper": 0.02}], None, "mm"),
    ("低于10件就补料", [{"band": "reject", "upper": 10.0, "upper_inclusive": False}], None, "件"),
])
def test_parse_criterion_answer(text, limits, expected, unit):
    assert parse_criterion_answer(text) == {"limits": limits, "expected": expected, "unit": unit}


def test_parse_criterion_answer_never_invents_numbers():
    assert parse_criterion_answer("主要靠听声音，不对劲就停") == {"limits": [], "expected": None, "unit": None}


@pytest.mark.parametrize("text,iso", [
    ("4 小时", "PT4H"), ("最晚4小时", "PT4H"), ("半小时", "PT30M"), ("三天之内", "P3D"),
    ("一个半小时", "PT90M"), ("两周", "P14D"), ("十二小时", "PT12H"), ("30分钟", "PT30M"),
])
def test_parse_duration(text, iso):
    assert parse_duration(text) == iso


@pytest.mark.parametrize("text", ["一个班之内", "尽快", "看情况"])
def test_parse_duration_does_not_guess(text):
    # Shift length differs per site; "尽快" has no number -- both stay text-only.
    assert parse_duration(text) is None


# --- interview flow ---------------------------------------------------------------------------

def _turn(client, wid, text):
    r = client.post(f"/api/expert-workflows/{wid}/turns", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


def _to_criterion_question(client):
    """Background -> 3 steps -> end -> a branch after step 2 -> no parallel -> approval after
    step 3 -> no retry; the next question is the criterion follow-up."""
    wid = client.post("/api/expert-workflows", json={}).json()["id"]
    for t in ["设备/质量异常", "CNC 加工件尺寸超差", guide_service.GOAL_SKIP_CHIP, "无",
              "停机", "复测尺寸", "调整刀补", END_CHIP, "恢复生产",
              "复测尺寸", "偏差小", "偏差大，换刀", "调整刀补",
              NO_PARALLEL_CHIP, "调整刀补", "质量主管", guide_service.NO_RETRY_CHIP]:
        r = _turn(client, wid, t)
    assert r["next_question"]["target"] == "criterion_discovery"
    return wid


def _node(client, wid, node_type):
    graph = client.get(f"/api/expert-workflows/{wid}").json()["graph"]
    return next(n for n in graph["nodes"] if n["node_type"] == node_type)


def test_declining_both_follow_ups_records_nothing(client):
    wid = _to_criterion_question(client)
    r = _turn(client, wid, guide_service.NO_CRITERION_CHIP)
    assert r["next_question"]["target"] == "timing_discovery"
    r = _turn(client, wid, guide_service.NO_TIME_LIMIT_CHIP)
    assert r["next_question"]["target"] == "experience_discovery"   # no escalation question
    assert _node(client, wid, "decision")["evaluation_criteria"] == []
    assert _node(client, wid, "approval")["sla_config"] is None


def test_a_no_that_carries_a_number_is_an_answer(client):
    wid = _to_criterion_question(client)
    _turn(client, wid, "没超过0.05mm就行")
    crit = _node(client, wid, "decision")["evaluation_criteria"][0]
    assert crit["limits"] == [{"band": "reject", "lower": 0.05, "lower_inclusive": False}]
    assert crit["description"] == "没超过0.05mm就行"


def test_unparseable_answers_are_kept_verbatim_without_numbers(client):
    wid = _to_criterion_question(client)
    _turn(client, wid, "主要看铁屑颜色")
    crit = _node(client, wid, "decision")["evaluation_criteria"][0]
    assert crit["type"] == "text" and "limits" not in crit and crit["description"] == "主要看铁屑颜色"
    r = _turn(client, wid, "一个班之内")
    assert r["next_question"]["target"] == "escalation_discovery"
    r = _turn(client, wid, guide_service.NO_ESCALATION_CHIP)
    sla = _node(client, wid, "approval")["sla_config"]
    assert "duration" not in sla and sla["description"] == "一个班之内" and sla["violation_action"] == "none"
    assert r["next_question"]["target"] == "experience_discovery"


# Declines phrased the way experts actually answered in an end-to-end run with a real model:
# filler before the "no", or "没有…要求" mid-sentence. A "no" that carries a number still counts.
@pytest.mark.parametrize("text", ["这个没有明确的时间要求，班组长一般就在现场。", "时间上没有硬性要求", "没有明确的时间要求"])
def test_sla_decline_with_filler(text):
    assert sla_from_answer(text) is None


def test_sla_answers_still_recorded():
    assert sla_from_answer("没超过两小时就行")["duration"] == "PT2H"
    sla = sla_from_answer("首件送过去以后半小时内质检要给结论，半小时还没签就打电话报给质量主管。")
    assert sla["duration"] == "PT30M" and sla["escalate_to_role"] == "质量主管"
    assert sla_from_answer("当天要签完") == {"type": "deadline", "from_trigger": "previous_node_completed", "description": "当天要签完"}


def test_criterion_decline_with_filler():
    assert criterion_from_answer({"label": "x"}, "这个没有具体数值，靠经验看") is None
    assert criterion_from_answer({"label": "x"}, "主要看铁屑颜色")["type"] == "text"
