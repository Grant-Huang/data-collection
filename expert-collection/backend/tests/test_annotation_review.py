"""Annotation on the review loop (IMPLEMENTATION_PLAN.md section 17.4), with scripted model
responses: blind double annotation, corrections carried as graphs, agreement / arbitration /
rejection, stale sessions, and legacy verdict-only annotations."""
import copy
import json
from pathlib import Path

import pytest

from app import llm_client, review_agent

SAMPLE = json.loads((Path(__file__).resolve().parents[3] / "docs/expert-workflow-collection/schema/workflow_graph_v2_sample.json").read_text())


@pytest.fixture
def version(client):
    base = SAMPLE["records"][0]
    records = []
    for i, name in enumerate(["设备报警处理", "来料检验不合格", "换线首件确认"]):
        r = copy.deepcopy(base)
        r["record_id"] = f"rec_{i}"
        r["scenario"]["scenario_name"] = name
        r["scenario"]["trigger"] = f"{name} 触发"
        for n in r["graph"]["nodes"]:
            n["label"] = f"{n['label']}（{name}）"
        r.setdefault("provenance", {})["source_type"] = "public_extracted"
        records.append(r)
    payload = {"dataset_meta": {**SAMPLE["dataset_meta"], "source_type": "public_extracted"}, "records": records}
    res = client.post("/api/datasets/import/confirm", json={"payload": payload, "import_records_without_errors": True})
    assert res.status_code == 200, res.text
    return res.json()["id"]


class Scripted:
    def __init__(self):
        self.queue = []

    def __call__(self, cfg, messages, timeout=None):
        return self.queue.pop(0)


@pytest.fixture
def model(monkeypatch):
    fake = Scripted()
    monkeypatch.setattr(review_agent, "_slot", lambda slot: {"enabled": True, "endpoint": "http://x", "model_name": "m", "api_key": "k"})
    monkeypatch.setattr(llm_client, "chat_completion_json", fake)
    return fake


def _start(client, vid, rid, name, expect=200):
    r = client.post(f"/api/datasets/versions/{vid}/records/{rid}/review-session", json={"annotator_name": name})
    assert r.status_code == expect, r.text
    return r.json()


def _say(client, vid, sid, text, expect=200):
    r = client.post(f"/api/datasets/versions/{vid}/review-sessions/{sid}/turns", json={"text": text})
    assert r.status_code == expect, r.text
    return r.json()


def _detail(client, vid, rid):
    return client.get(f"/api/datasets/versions/{vid}/records/{rid}").json()


def _rename_n3(new_label):
    """Model response: the annotator says step n3 is actually called something else."""
    return {"intent": "edit", "understanding": "您是说复测这一步应该叫别的名字。",
            "ops": [{"op": "update_node", "node_id": "n3", "patch": {"label": new_label}}],
            "evidence": {}, "resolved_gap_ids": [], "question": None, "new_uncertainties": [],
            "reason_tags": ["unclear_label"]}


def test_both_accept_is_gold_and_blind(client, version):
    s1 = _start(client, version, "rec_0", "alice")
    assert s1["phase"] == "final_confirm" and s1["proposal"]["verdict"] == "accepted"
    assert "1. " in s1["turns"][0]["body"]  # read-back of the graph under review
    s1 = _say(client, version, s1["session_id"], "确认")  # no model needed
    assert s1["status"] == "submitted"

    d = _detail(client, version, "rec_0")
    assert d["stage"] == "second_review" and d["blind"] and d["annotations"] == []
    _start(client, version, "rec_0", " Alice ", expect=400)  # same person can't be second

    s2 = _start(client, version, "rec_0", "bob")
    assert all(t["role"] == "assistant" for t in s2["turns"])  # nothing of alice's in bob's session
    _say(client, version, s2["session_id"], "确认")
    d = _detail(client, version, "rec_0")
    assert d["stage"] == "done" and d["gold_status"] == "gold" and d["final_verdict"] == "accepted" and d["final_graph"] is None


def test_same_correction_by_both_is_gold_with_corrected_graph(client, version, model):
    for name in ("alice", "bob"):
        s = _start(client, version, "rec_1", name)
        model.queue.append(_rename_n3("质量工程师复测尺寸（来料检验不合格）"))
        s = _say(client, version, s["session_id"], "复测那一步应该写清楚是复测尺寸")
        assert s["proposal"]["verdict"] == "needs_revision" and s["proposal"]["reason_tags"] == ["unclear_label"]
        assert any("改为" in c for c in s["turns"][-1]["changes"])
        s = _say(client, version, s["session_id"], "确认")
        assert s["status"] == "submitted"
    d = _detail(client, version, "rec_1")
    assert d["stage"] == "done" and d["gold_status"] == "gold" and d["final_verdict"] == "needs_revision"
    assert any(n["label"] == "质量工程师复测尺寸（来料检验不合格）" for n in d["final_graph"]["nodes"])
    assert d["annotations"][0]["changes"] and d["annotations"][0]["revised_graph"]


def test_disagreement_goes_to_arbitration_and_arbitrator_adopts_a_version(client, version, model):
    s = _start(client, version, "rec_2", "alice")
    model.queue.append(_rename_n3("质量工程师复测尺寸"))
    s = _say(client, version, s["session_id"], "复测那一步要写清楚")
    _say(client, version, s["session_id"], "确认")
    s = _start(client, version, "rec_2", "bob")
    _say(client, version, s["session_id"], "确认")  # bob accepts as is

    d = _detail(client, version, "rec_2")
    assert d["stage"] == "arbitration" and not d["blind"]
    _start(client, version, "rec_2", "alice", expect=400)  # independents can't arbitrate

    arb = _start(client, version, "rec_2", "carol")
    assert arb["role_in_process"] == "arbitration"
    assert "alice" in arb["turns"][0]["body"] and "bob" in arb["turns"][0]["body"]
    alice_id = d["annotations"][0]["annotation_id"]

    # A second would-be arbitrator opens a session too, but carol finishes first.
    other = _start(client, version, "rec_2", "dave")

    model.queue.append({"intent": "adopt", "adopt_annotation_id": alice_id, "understanding": "您是说用 alice 的版本。",
                        "ops": [], "evidence": {}, "resolved_gap_ids": [], "question": None, "new_uncertainties": [],
                        "reason_tags": ["unclear_label"]})
    arb = _say(client, version, arb["session_id"], "用 alice 的版本")
    assert arb["proposal"]["verdict"] == "needs_revision"
    arb = _say(client, version, arb["session_id"], "确认")
    d = _detail(client, version, "rec_2")
    assert d["stage"] == "done" and d["gold_status"] == "gold"
    assert any(n["label"] == "质量工程师复测尺寸" for n in d["final_graph"]["nodes"])

    _say(client, version, other["session_id"], "确认", expect=409)  # record moved on -> stale

    summary = client.get(f"/api/datasets/versions/{version}/annotation-summary").json()
    assert summary["corrected_count"] == 1 and summary["stage_counts"]["done"] == 1


def test_reject_by_saying_so(client, version):
    s = _start(client, version, "rec_0", "alice")
    s = _say(client, version, s["session_id"], "这条不能用")
    assert s["phase"] == "final_confirm" and s["proposal"] == {"verdict": "rejected", "reason_tags": ["out_of_scope"]}
    s = _say(client, version, s["session_id"], "确认")
    assert s["status"] == "submitted"


def test_legacy_verdict_only_revisions_go_to_arbitration(client, version):
    for name in ("alice", "bob"):
        r = client.post(f"/api/datasets/versions/{version}/records/rec_0/annotations",
                        json={"verdict": "needs_revision", "reason_tags": ["missing_step"], "annotator_name": name})
        assert r.status_code == 200
    d = _detail(client, version, "rec_0")
    assert d["stage"] == "arbitration"  # agreed "needs revision" but nobody produced the corrected graph


def test_without_model_only_short_intents_work(client, version):
    s = _start(client, version, "rec_0", "alice")
    s = _say(client, version, s["session_id"], "第三步其实是班长做的")
    assert "没有配置可用的 AI 模型" in s["turns"][-1]["body"] and s["graph"] == s["base_graph"]


def test_export_carries_original_and_gold_graph(client, version, model):
    """Section 17.8: export keeps `graph` as collected and adds `gold_graph` + outcome."""
    import jsonschema
    from app import import_pipeline

    for name in ("alice", "bob"):  # same correction by both -> Gold with the corrected graph
        s = _start(client, version, "rec_1", name)
        model.queue.append(_rename_n3("质量工程师复测尺寸（来料检验不合格）"))
        _say(client, version, s["session_id"], "复测那一步应该写清楚是复测尺寸")
        _say(client, version, s["session_id"], "确认")
    s = _start(client, version, "rec_0", "alice")  # rec_0: only one annotation so far
    _say(client, version, s["session_id"], "确认")

    for fmt in ("raw", "role_normalized", "anonymized"):
        r = client.get(f"/api/datasets/versions/{version}/export?format={fmt}")
        assert r.status_code == 200, r.text
        payload = r.json()
        recs = {x["record_id"]: x for x in payload["records"]}
        corrected, pending, untouched = recs["rec_1"], recs["rec_0"], recs["rec_2"]
        labels = lambda g: {n["label"] for n in g["nodes"]}
        assert "质量工程师复测（来料检验不合格）" in labels(corrected["graph"])          # original kept
        assert "质量工程师复测尺寸（来料检验不合格）" in labels(corrected["gold_graph"])  # Gold = corrected
        expected = {"gold_status": "gold", "final_verdict": "needs_revision", "corrected": True,
                    "reason_tags": ["unclear_label"], "annotator_count": 2}
        assert {k: corrected["annotation"][k] for k in expected} == expected
        assert pending["gold_graph"] is None and pending["annotation"]["gold_status"] == "pending_second_review"
        assert pending["annotation"]["final_verdict"] is None and pending["annotation"]["reason_tags"] == []  # nothing leaks early
        assert untouched["gold_graph"] is None and untouched["annotation"]["annotator_count"] == 0
        # Every format, the anonymized one included (its text experience buckets are allowed by
        # schema v2), must stay re-importable.
        jsonschema.validate({k: v for k, v in payload.items() if k != "export_format"}, import_pipeline._load_schema())
    assert recs["rec_1"]["provenance"]["expert_years_experience"] == "10-20年"  # anonymized: bucketed


def test_schema_allows_exactly_the_experience_buckets():
    """schema v2 lists the anonymized buckets verbatim; keep it in step with anonymize.py."""
    from app import anonymize, import_pipeline

    field = import_pipeline._load_schema()["$defs"]["workflow_record"]["properties"]["provenance"]["properties"]["expert_years_experience"]
    enum = next(a["enum"] for a in field["anyOf"] if a.get("type") == "string")
    assert {anonymize.bucket_experience_years(y) for y in range(0, 60)} == set(enum)
