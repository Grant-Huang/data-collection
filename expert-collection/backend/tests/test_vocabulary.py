"""Accumulated vocabulary and ontology entries (app/vocabulary.py): append-only, built from
confirmed expert workflows and annotations, never written back into records."""
import copy

from app import db, vocabulary
from tests.test_review_ontology import EXTRACTED, NARRATIVE, _answer, _turn, model  # noqa: F401  (fixture)

GRAPH = copy.deepcopy(EXTRACTED)
for n in GRAPH["nodes"]:
    if n["node_id"] == "n4":
        n["evaluation_criteria"] = [{"id": "c1", "name": "外径", "type": "numeric_range", "unit": "mm",
                                     "description": "外径正常 20.00mm", "expected": {"target": 20.0}}]
    if n["node_id"] == "n5":
        n["sla_config"] = {"type": "deadline", "duration": "PT2H", "violation_action": "escalate",
                           "escalate_to_role": "车间主任", "description": "2小时内要签，超时找车间主任"}

SRC = {"type": "expert_workflow", "id": "w1", "name": "首件确认"}


def _terms(kind):
    return {e["label"]: e for e in vocabulary.list_entries("term", kind)}


def test_terms_and_ontology_from_graph():
    vocabulary.accumulate_graph(GRAPH, SRC)
    assert set(_terms("role")) == {"操作员", "质量员", "工艺工程师", "车间主任"}
    assert "做首件" in _terms("step") and "关键尺寸合格吗" in _terms("decision")
    assert _terms("check")["外径"]["steps"] == ["尺寸是否合格"]
    assert "mm" in _terms("unit") and "尺寸不合格" in _terms("condition")
    checks = vocabulary.list_entries("ontology", "checks")
    assert len(checks) == 1 and checks[0]["content"]["expected"] == {"target": 20.0}
    assert "check_id" not in checks[0]["content"]  # per-workflow ids are not part of the entry
    tcs = vocabulary.list_entries("ontology", "time_constraints")
    assert tcs[0]["label"] == "2小时内要签，超时找车间主任" and tcs[0]["steps"] == ["工艺工程师签字放行"]


def test_same_source_twice_changes_no_counts_and_nothing_is_removed():
    vocabulary.accumulate_graph(GRAPH, SRC)
    vocabulary.accumulate_graph(GRAPH, SRC)
    assert _terms("role")["操作员"]["source_count"] == 1
    # The workflow is later edited: a role renamed. The old name stays (append-only).
    renamed = copy.deepcopy(GRAPH)
    for n in renamed["nodes"]:
        n["actor_roles"] = ["质检员" if r == "质量员" else r for r in n.get("actor_roles") or []]
    vocabulary.accumulate_graph(renamed, SRC)
    roles = _terms("role")
    assert "质量员" in roles and "质检员" in roles and roles["操作员"]["source_count"] == 1
    # A second workflow using the same word counts as a second source.
    vocabulary.accumulate_graph(GRAPH, {"type": "expert_workflow", "id": "w2", "name": "x"})
    assert _terms("role")["操作员"]["source_count"] == 2
    assert vocabulary.list_entries("ontology", "checks")[0]["source_count"] == 2


def test_annotation_rules():
    base = {"annotation_id": "a1", "version_id": "v1", "record_id": "r1"}
    vocabulary.accumulate_from_annotation({**base, "verdict": "rejected"}, GRAPH)
    vocabulary.accumulate_from_annotation({**base, "annotation_id": "a2", "verdict": "needs_revision"}, GRAPH)
    assert vocabulary.list_entries("term") == []  # rejected / revision without a corrected graph: nothing
    vocabulary.accumulate_from_annotation({**base, "annotation_id": "a3", "verdict": "accepted"}, GRAPH, "首件")
    src = _terms("role")["操作员"]["sources"][0]
    assert src["type"] == "annotation" and src["name"] == "首件" and src["record_id"] == "r1"


def test_confirming_a_workflow_accumulates_without_touching_it(client, model):
    rec = client.post("/api/expert-workflows", json={}).json()
    rec = _turn(client, rec["id"], NARRATIVE)
    wid = rec["id"]
    assert vocabulary.list_entries("term") == []  # drafts don't count
    rec = _turn(client, wid, "没问题")
    before = db.get(wid)
    rec = _turn(client, wid, "确认")
    assert rec["status"] == "expert_confirmed"
    assert db.get(wid)["graph"] == {**before["graph"], "nodes": [dict(n, expert_confirmed=True) for n in before["graph"]["nodes"]],
                                    "edges": [dict(e, expert_confirmed=True) for e in before["graph"]["edges"]]}
    assert _terms("role")["质量员"]["sources"][0]["id"] == wid

    summary = client.get("/api/vocabulary/summary").json()
    assert summary["counts"]["term"]["role"]["count"] == 3 and summary["kinds"]["term"]["role"] == "角色"
    assert client.get("/api/vocabulary/term?kind=role").status_code == 200
    assert client.get("/api/vocabulary/nope").status_code == 404
    assert client.get("/api/vocabulary/term?kind=nope").status_code == 400

    # Backfill over existing records is idempotent.
    r = client.post("/api/vocabulary/backfill?actor_role=admin").json()
    assert r == {"workflows": 1, "annotations": 0}
    assert _terms("role")["质量员"]["source_count"] == 1
