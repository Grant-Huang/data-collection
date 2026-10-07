"""刷新工作流图 ("regenerate graph") sometimes produced a wrong or outright rejected graph
whenever the transcript described a rework/retry loop.

Root cause: _REGENERATE_SYSTEM_PROMPT's rule text told the model "express rework via
retry_semantics, never build a back-edge", but the JSON schema it was given to fill in never
defined a retry_semantics field at all -- so a model asked to describe a rework loop had no
legal way to comply. It would either drop the rework path silently (a wrong graph that still
validates) or build a back-edge anyway (a cycle that graph_validator rejects, failing the
*whole* regeneration with a structural-validation error). These tests cover the fix:
_REGENERATE_SYSTEM_PROMPT now documents the field, and guide_service.regenerate_graph_from_
transcript reads it back the same way review_agent.extract_from_narrative already did for the
narrative-based path.
"""
from app import guide_service, llm_client


def _raw_node(node_id, node_type, label, retry_semantics=None):
    return {"node_id": node_id, "node_type": node_type, "label": label, "actor_roles": [],
            "retry_semantics": retry_semantics}


def test_coerce_regenerated_graph_does_not_itself_set_retry_semantics():
    """Documented contract (see its docstring): the raw coercion step never touches this field
    -- it's the caller's job to layer it on afterward. Regression guard for that contract."""
    parsed = {
        "nodes": [_raw_node("n1", "start", "开始"),
                  _raw_node("n2", "activity", "复测", retry_semantics={"enabled": True, "rework_reference_node_id": "n1"}),
                  _raw_node("n3", "end", "结束")],
        "edges": [{"edge_id": "e1", "from": "n1", "to": "n2", "edge_type": "normal"},
                  {"edge_id": "e2", "from": "n2", "to": "n3", "edge_type": "normal"}],
        "start_node_ids": ["n1"], "end_node_ids": ["n3"],
    }
    graph = guide_service._coerce_regenerated_graph(parsed)
    assert graph is not None
    assert all("retry_semantics" not in n for n in graph["nodes"])


def test_apply_retry_semantics_sets_it_and_validates_the_reference():
    parsed_nodes = [
        _raw_node("n1", "start", "开始"),
        _raw_node("n2", "activity", "复测", retry_semantics={
            "enabled": True, "rework_reference_node_id": "n1", "condition": "尺寸超差", "description": "重新加工",
        }),
        _raw_node("n3", "end", "结束"),
    ]
    graph = guide_service._coerce_regenerated_graph({
        "nodes": parsed_nodes,
        "edges": [{"edge_id": "e1", "from": "n1", "to": "n2", "edge_type": "normal"},
                  {"edge_id": "e2", "from": "n2", "to": "n3", "edge_type": "normal"}],
        "start_node_ids": ["n1"], "end_node_ids": ["n3"],
    })
    raw_by_id = {n["node_id"]: n for n in parsed_nodes}
    guide_service._apply_retry_semantics(graph, raw_by_id)

    by_id = {n["node_id"]: n for n in graph["nodes"]}
    assert by_id["n2"]["retry_semantics"] == {
        "enabled": True, "rework_reference_node_id": "n1", "condition": "尺寸超差", "description": "重新加工",
    }
    assert "retry_semantics" not in by_id["n1"] and "retry_semantics" not in by_id["n3"]

    # No back-edge was needed to express the rework -- the graph stays a plain DAG.
    from app import graph_validator
    assert graph_validator.is_valid(graph)


def test_apply_retry_semantics_nulls_a_dangling_reference_instead_of_trusting_the_model():
    parsed_nodes = [
        _raw_node("n1", "start", "开始"),
        _raw_node("n2", "activity", "复测", retry_semantics={"enabled": True, "rework_reference_node_id": "does-not-exist"}),
        _raw_node("n3", "end", "结束"),
    ]
    graph = guide_service._coerce_regenerated_graph({
        "nodes": parsed_nodes,
        "edges": [{"edge_id": "e1", "from": "n1", "to": "n2", "edge_type": "normal"},
                  {"edge_id": "e2", "from": "n2", "to": "n3", "edge_type": "normal"}],
        "start_node_ids": ["n1"], "end_node_ids": ["n3"],
    })
    guide_service._apply_retry_semantics(graph, {n["node_id"]: n for n in parsed_nodes})
    by_id = {n["node_id"]: n for n in graph["nodes"]}
    assert by_id["n2"]["retry_semantics"]["rework_reference_node_id"] is None


def test_apply_retry_semantics_resolves_a_forward_reference():
    """The rework target doesn't have to appear earlier in the model's own node list -- the
    reference is checked against the *complete* node set, not resolved node-by-node."""
    parsed_nodes = [
        _raw_node("n1", "activity", "复测", retry_semantics={"enabled": True, "rework_reference_node_id": "n2"}),
        _raw_node("n2", "start", "开始"),  # listed *after* the node that references it
    ]
    graph = guide_service._coerce_regenerated_graph({
        "nodes": parsed_nodes,
        "edges": [{"edge_id": "e1", "from": "n2", "to": "n1", "edge_type": "normal"}],
        "start_node_ids": ["n2"], "end_node_ids": [],
    })
    guide_service._apply_retry_semantics(graph, {n["node_id"]: n for n in parsed_nodes})
    by_id = {n["node_id"]: n for n in graph["nodes"]}
    assert by_id["n1"]["retry_semantics"]["rework_reference_node_id"] == "n2"


def test_regenerate_graph_from_transcript_round_trips_retry_semantics(monkeypatch):
    """End-to-end through the real function (not the test suite's usual shortcut of monkey-
    patching regenerate_graph_from_transcript itself) -- exercises the actual prompt/schema and
    would have caught the missing-field bug."""
    monkeypatch.setattr(
        guide_service.app_settings, "resolve_slot_for_call",
        lambda settings, slot: {"enabled": True, "endpoint": "http://x", "model_name": "m", "temperature": 0.1},
    )
    response = {
        "nodes": [
            _raw_node("n1", "start", "设备报警"),
            _raw_node("n2", "activity", "复测尺寸"),
            _raw_node("n3", "activity", "返工", retry_semantics={
                "enabled": True, "rework_reference_node_id": "n2", "condition": "复测仍超差",
            }),
            _raw_node("n4", "end", "恢复生产"),
        ],
        "edges": [
            {"edge_id": "e1", "from": "n1", "to": "n2", "edge_type": "normal"},
            {"edge_id": "e2", "from": "n2", "to": "n3", "edge_type": "normal"},
            {"edge_id": "e3", "from": "n3", "to": "n4", "edge_type": "normal"},
        ],
        "start_node_ids": ["n1"], "end_node_ids": ["n4"],
    }
    monkeypatch.setattr(llm_client, "chat_completion_json", lambda cfg, messages, timeout=None: response)

    graph = guide_service.regenerate_graph_from_transcript([{"role": "expert", "text": "不重要，已 mock"}])

    from app import graph_validator
    assert graph_validator.is_valid(graph)  # no back-edge was ever needed
    by_id = {n["node_id"]: n for n in graph["nodes"]}
    assert by_id["n3"]["retry_semantics"] == {
        "enabled": True, "rework_reference_node_id": "n2", "condition": "复测仍超差", "description": None,
    }
