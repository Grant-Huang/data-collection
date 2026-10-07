"""Manufacturing Operational Ontology v1 (docs/expert-workflow-collection/ontology/
MANUFACTURING_OPERATIONAL_ONTOLOGY.md): the v3 JSON Schema, the v2 -> v3 lift, the validator's
rule table, and the read-only GET .../ontology endpoint."""
import copy
import json
from pathlib import Path

import jsonschema
import pytest

from app import guide_service, ontology, ontology_validator

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "docs" / "expert-workflow-collection" / "schema"


def _load(name):
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def _codes(issues):
    return {i["code"] for i in issues}


def _v3_record():
    return copy.deepcopy(_load("workflow_graph_v3_sample.json")["records"][0])


# --- schema ------------------------------------------------------------------------------

def test_v3_schema_is_valid_and_accepts_both_v3_and_v2_samples():
    validator = jsonschema.Draft202012Validator(_load("workflow_graph_schema_v3.json"))
    validator.check_schema(validator.schema)
    assert list(validator.iter_errors(_load("workflow_graph_v3_sample.json"))) == []
    # Backward compatibility: every v2 document is still a valid v3 document.
    assert list(validator.iter_errors(_load("workflow_graph_v2_sample.json"))) == []


def test_v3_schema_rejects_a_bad_duration():
    validator = jsonschema.Draft202012Validator(_load("workflow_graph_schema_v3.json"))
    doc = _load("workflow_graph_v3_sample.json")
    doc["records"][0]["ontology"]["time_constraints"][0]["duration"] = "4 hours"
    assert any("duration" in list(e.absolute_path) for e in validator.iter_errors(doc))


# --- threshold text parsing ----------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("15-35", ({"lower": 15.0, "upper": 35.0}, None)),
    ("15~35°C", ({"lower": 15.0, "upper": 35.0}, "°C")),
    (">= 1.33", ({"lower": 1.33}, None)),
    ("≥1.33", ({"lower": 1.33}, None)),
    ("> 50%", ({"lower": 50.0, "lower_inclusive": False}, "%")),
    ("<2°C", ({"upper": 2.0, "upper_inclusive": False}, "°C")),
])
def test_parse_threshold_text_simple_forms(text, expected):
    assert ontology.parse_threshold_text(text) == expected


@pytest.mark.parametrize("text", ["设备状态正常", "", None, "约 30 左右"])
def test_parse_threshold_text_refuses_to_guess(text):
    assert ontology.parse_threshold_text(text) is None


# --- the shipped v3 sample is clean ---------------------------------------------------------

def test_v3_sample_lifts_without_errors():
    rec = _v3_record()
    view = ontology.lift_v2_record(rec)
    issues = ontology_validator.validate(view, rec["graph"])
    assert [i for i in issues if i["level"] == "error"] == []
    # The explicit registry is kept as-is (lift only adds what's missing).
    assert {c.check_id for c in view.ontology.checks} >= {"chk_cpk", "chk_first_article"}
    assert view.node_links["n_quality_release"].permission_ids == ["perm_quality_release"]


# --- v2 / Phase 3-A lift --------------------------------------------------------------------

def _v2_record():
    return {
        "manufacturing_context": {"industry": "汽车零部件", "process_area": "机加工"},
        "graph": {
            "nodes": [
                {"node_id": "a", "node_type": "activity", "label": "加工", "actor_roles": ["操作工"],
                 "evidence": ["我们先上料再加工"], "source_turn_ids": ["t1"], "confidence": 0.9},
                {"node_id": "q", "node_type": "approval", "label": "质量放行", "actor_roles": ["质量工程师"],
                 "evaluation_criteria": [{"id": "cpk", "name": "CPK", "type": "metric",
                                          "thresholds": {"normal": ">= 1.33", "warning": "1.0-1.33"}}],
                 "sla_config": {"type": "deadline", "duration": "PT4H", "from_trigger": "previous_node_completed",
                                "violation_action": "escalate"},
                 "approval_matrix": [{"approval_type": "quality_release", "required_roles": ["质量工程师"],
                                      "sequence": "sequential", "criteria": "首件合格", "escalation_level": 1}],
                 "retry_semantics": {"enabled": True, "is_temporary": True, "condition": "设备故障跳过温度检测",
                                     "expiration": {"duration": "PT72H", "lot_count": 3},
                                     "escalation_on_repeat": {"enabled": True, "action": "create_capa"}},
                 "containment_scope": {"dimension": "equipment_id", "rule": "all_products_on_same_equipment"}},
                {"node_id": "h", "node_type": "activity", "label": "隔离分析"},
            ],
            "edges": [
                {"edge_id": "e1", "from": "a", "to": "q", "edge_type": "normal"},
                {"edge_id": "e2", "from": "q", "to": "h", "edge_type": "exception_forward", "condition": "CPK < 1.0"},
            ],
        },
    }


def test_lift_maps_every_phase3a_field_into_the_registry():
    view = ontology.lift_v2_record(_v2_record())
    ont = view.ontology

    assert {r.name for r in ont.roles} == {"操作工", "质量工程师"}
    assert ont.scopes[0].selectors == {"industry": ["汽车零部件"], "process_area": ["机加工"]}

    chk = ont.checks[0]
    assert chk.check_id == "chk_q_cpk" and chk.kind == "numeric" and chk.source_criterion_id == "cpk"
    assert [(b.band, b.lower, b.upper) for b in chk.limits] == [("normal", 1.33, None), ("warning", 1.0, 1.33)]
    assert chk.limits_text == {"normal": ">= 1.33", "warning": "1.0-1.33"}

    tc = ont.time_constraints[0]
    assert (tc.kind, tc.duration, tc.anchor) == ("deadline", "PT4H", "previous_node_completed")
    assert tc.on_violation.escalation_policy_id == "esc_q_sla"

    perm = ont.permissions[0]
    assert perm.action == "approve" and perm.allowed_role_ids == ["role_质量工程师"]
    assert perm.submission_criteria[0].description == "首件合格"

    exc_ids = {x.exception_id for x in ont.exception_cases}
    assert exc_ids == {"exc_q", "exc_e2"}
    temp_exc = next(x for x in ont.exception_cases if x.exception_id == "exc_q")
    assert temp_exc.temporary_measure["expiration"]["duration"] == "PT72H"
    assert temp_exc.containment["dimension"] == "equipment_id"
    assert next(x for x in ont.exception_cases if x.exception_id == "exc_e2").handler_node_id == "h"

    links = view.node_links["q"]
    assert links.check_ids == ["chk_q_cpk"] and links.permission_ids == ["perm_q_1"]
    assert set(links.exception_ids) == {"exc_q", "exc_e2"}
    assert view.edge_links["e2"].exception_id == "exc_e2"

    a = view.node_links["a"]
    assert a.assertion.confidence_basis == "expert_stated"
    assert ont.evidence[0].content == "我们先上料再加工" and a.assertion.evidence_ids == ["ev_a_1"]


def test_lift_is_deterministic_and_does_not_mutate_the_record():
    rec = _v2_record()
    before = copy.deepcopy(rec)
    assert ontology.lift_v2_record(rec) == ontology.lift_v2_record(rec)
    assert rec == before


def test_lifted_v2_has_no_errors_only_gaps_to_fill():
    rec = _v2_record()
    issues = ontology_validator.validate(ontology.lift_v2_record(rec), rec["graph"])
    assert [i for i in issues if i["level"] == "error"] == []
    # v2 never says who an escalation goes to -- reported, not invented.
    assert "ont_escalation_missing_role" in _codes(issues)


def test_lift_turns_a_named_approver_into_a_permission():
    graph = {"nodes": [{"node_id": "ap", "node_type": "approval", "label": "审批（质量主管）",
                        "actor_roles": ["质量主管"]}], "edges": []}
    view = ontology.lift_v2_record({"graph": graph})
    assert view.node_links["ap"].permission_ids == ["perm_ap_approver"]
    assert view.ontology.permissions[0].allowed_role_ids == ["role_质量主管"]
    assert "ont_approval_without_permission" not in _codes(ontology_validator.validate(view, graph))


# --- validator rules ------------------------------------------------------------------------

def _issues_after(mutate):
    rec = _v3_record()
    mutate(rec)
    return _codes(ontology_validator.validate(ontology.lift_v2_record(rec), rec["graph"]))


def _find(items, key, value):
    return next(i for i in items if i[key] == value)


def test_rule_dangling_ref():
    def m(rec):
        _find(rec["graph"]["nodes"], "node_id", "n_quality_release")["check_ids"].append("chk_nope")
    assert "ont_dangling_ref" in _issues_after(m)


def test_rule_check_missing_unit_and_inverted_limit_and_expected_outside_normal():
    def m(rec):
        cpk = _find(rec["ontology"]["checks"], "check_id", "chk_cpk")
        cpk.pop("unit")
        cpk["expected"]["target"] = 0.5
        cpk["limits"][1]["lower"] = 2.0
    codes = _issues_after(m)
    assert {"ont_check_missing_unit", "ont_limit_inverted", "ont_expected_outside_normal"} <= codes


def test_rule_temporary_measure_must_expire():
    def m(rec):
        temp = _find(rec["ontology"]["exception_cases"], "exception_id", "exc_temp_out_of_range")["temporary_measure"]
        temp.pop("expiration")
        temp.pop("revocation_trigger")
    assert "ont_temp_measure_no_expiry" in _issues_after(m)


def test_rule_bad_duration():
    def m(rec):
        rec["ontology"]["time_constraints"][0]["duration"] = "4h"
    assert "ont_bad_duration" in _issues_after(m)


def test_rule_escalation_levels_must_increase():
    def m(rec):
        _find(rec["ontology"]["escalation_policies"], "policy_id", "esc_release_overdue")["levels"][1]["level"] = 1
    assert "ont_escalation_level_order" in _issues_after(m)


def test_rule_permission_needs_roles_and_approval_needs_permission():
    def m(rec):
        _find(rec["ontology"]["permissions"], "permission_id", "perm_process_release")["allowed_role_ids"] = []
        node = _find(rec["graph"]["nodes"], "node_id", "n_equipment_release")
        node["permission_ids"] = []
        node["actor_roles"] = []  # a named approver alone would be lifted into a Permission
    codes = _issues_after(m)
    assert {"ont_permission_no_roles", "ont_approval_without_permission"} <= codes


def test_rule_separation_of_duties():
    # Make QE perform the work right before the QE-only release that demands separation of duties.
    def m(rec):
        proc = _find(rec["graph"]["nodes"], "node_id", "n_process_release")
        proc["node_type"] = "activity"
        proc["raci"] = {"responsible": ["role_qe"]}
    assert "ont_sod_violation" in _issues_after(m)


def test_rule_exception_unhandled_and_low_confidence():
    def m(rec):
        exc = _find(rec["ontology"]["exception_cases"], "exception_id", "exc_cpk_low")
        exc.pop("handler_node_id")
        exc.pop("escalation_policy_id")
        rec["graph"]["edges"] = [e for e in rec["graph"]["edges"] if e["edge_id"] != "e5"]
        _find(rec["graph"]["nodes"], "node_id", "n_process_release")["assertion"] = {"confidence": 0.3}
    codes = _issues_after(m)
    assert {"ont_exception_unhandled", "ont_low_confidence_no_evidence"} <= codes


def test_rule_decision_without_check():
    graph = {"nodes": [{"node_id": "d", "node_type": "decision", "label": "是否合格"},
                       {"node_id": "x", "node_type": "end", "label": "结束"}],
             "edges": [{"edge_id": "e", "from": "d", "to": "x", "edge_type": "conditional", "condition": "合格"}]}
    issues = ontology_validator.validate(ontology.lift_v2_record({"graph": graph}), graph)
    assert "ont_decision_without_check" in _codes(issues)


# --- endpoint -------------------------------------------------------------------------------

def test_ontology_endpoint_lifts_a_collected_workflow(client):
    wid = client.post("/api/expert-workflows", json={}).json()["id"]
    for text in ["设备/质量异常", "CNC 加工件尺寸超差，质检抽检发现的", guide_service.GOAL_SKIP_CHIP, "无", "班组长先停机"]:
        assert client.post(f"/api/expert-workflows/{wid}/turns", json={"text": text}).status_code == 200

    r = client.get(f"/api/expert-workflows/{wid}/ontology")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["schema_version"] == "3.0"
    assert body["ontology"]["scopes"][0]["scope_id"] == ontology.DEFAULT_SCOPE_ID
    graph = client.get(f"/api/expert-workflows/{wid}").json()["graph"]
    assert set(body["node_links"]) == {n["node_id"] for n in graph["nodes"]}
    assert all({"level", "code", "message"} <= set(i) for i in body["issues"])


def test_ontology_endpoint_404(client):
    assert client.get("/api/expert-workflows/nope/ontology").status_code == 404
