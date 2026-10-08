"""「您的讲述里我没找到…的原话」asked about step after step the expert plainly described.

Reported on a real session (wafer defect review): after 「刷新工作流图」 the interview asked,
one by one, whether 「SEM 复判看形貌」「复检完是否仍拿不准」「每日工程评审会定处置」
「所有决策回溯到机台、recipe、批次」「七天内把 CAPA 落下去」 were really said -- all of
them were, nearly word for word.

Root cause: the refreshed graph (guide_service.regenerate_graph_from_transcript) carried no
evidence quotes at all, and review_gaps treats a step without a quote as "a step nobody said",
the most severe tier, so every step went to the front of the queue. A secondary cause: quotes
were matched only verbatim, so a model quote that dropped one filler word also failed.
"""
from app import evidence, guide_service, llm_client, review_gaps

# The expert's narration from the report, verbatim.
NARRATION = (
    "嗯，我这么跟你讲吧。wafer 做完明场暗场扫描出来，第一步是缺陷分类，我们这边先走 ADC 自动分，分完还得人过一遍，"
    "准确率大概 95% 上下，碰到没见过的 pattern，系统会丢到 unknown 里，得人工贴标签。分完类，值班工程师两个小时之内"
    "要做初评，看缺陷密度、看落在哪个 die、是不是关键层。\n\n"
    "这里有个分支：如果单颗 wafer 缺陷数超过 30 颗，或者落在良率敏感区，再或者是新类型，那就不能自己拍板，必须触发复检，"
    "走 SEM 复判，把片子拿去看形貌。复检完还是拿不准的，就上每天的工程评审会，PE、设备、集成、良率的人都在，会上定处置："
    "放行、降级、返工还是直接报废，一般 48 小时内要有结论。\n\n"
    "异常情况也有，比如同一腔体连续三批冒同样的缺陷，那就立刻拉停线，走 MRB 加急处理，不走常规节奏。最后是闭环，"
    "所有决策都要回溯到机台、recipe、批次，七天内把 CAPA 落下去，不然这问题下个月还得再犯一遍。"
)


def test_verbatim_quotes_are_found():
    for quote in ["走 SEM 复判，把片子拿去看形貌", "复检完还是拿不准的", "上每天的工程评审会",
                  "所有决策都要回溯到机台、recipe、批次", "七天内把 CAPA 落下去"]:
        assert evidence.quote_found(quote, [NARRATION]), quote


def test_lightly_trimmed_quotes_are_found():
    """Models drop filler words or join nearby clauses; that is still the expert's wording."""
    for quote in ["SEM复判看形貌",                      # 走 / 把片子拿去 dropped
                  "所有决策要回溯到机台、Recipe、批次",    # 都 dropped, case changed
                  "复检完还拿不准",                       # 是 / 的 dropped
                  "七天内把CAPA落下去"]:                  # spacing
        assert evidence.quote_found(quote, [NARRATION]), quote


def test_quotes_the_expert_never_said_are_still_rejected():
    for quote in ["每周五召开质量例会", "通知客户并发出 8D 报告", "由厂长签字放行",
                  "缺陷数超过50颗",       # number changed (0.71 of the pieces match)
                  "值班工程师做终评"]:     # 初评 -> 终评 (0.57)
        assert not evidence.quote_found(quote, [NARRATION]), quote


def test_short_quotes_are_never_matched_loosely():
    # Three characters, two of them coincide with the narration: still not enough.
    assert not evidence.quote_found("拉停机", [NARRATION])
    assert evidence.quote_found("拉停线", [NARRATION])


def test_quote_must_come_from_the_expert_not_the_assistant(monkeypatch):
    monkeypatch.setattr(guide_service.app_settings, "resolve_slot_for_call",
                        lambda settings, slot: {"enabled": True, "endpoint": "http://x", "model_name": "m"})
    response = {
        "nodes": [{"node_id": "n1", "node_type": "start", "label": "开始", "evidence": None},
                  {"node_id": "n2", "node_type": "activity", "label": "发 8D 报告", "evidence": "发 8D 报告给客户"},
                  {"node_id": "n3", "node_type": "end", "label": "结束", "evidence": None}],
        "edges": [{"edge_id": "e1", "from": "n1", "to": "n2", "edge_type": "normal"},
                  {"edge_id": "e2", "from": "n2", "to": "n3", "edge_type": "normal"}],
        "start_node_ids": ["n1"], "end_node_ids": ["n3"],
    }
    monkeypatch.setattr(llm_client, "chat_completion_json", lambda cfg, messages, timeout=None: response)
    graph = guide_service.regenerate_graph_from_transcript([
        {"role": "assistant", "text": "要不要发 8D 报告给客户？"},
        {"role": "expert", "text": "这个我不清楚。"},
    ])
    assert next(n for n in graph["nodes"] if n["node_id"] == "n2")["evidence"] == []


def _regenerated_response():
    """What a model returns for the narration above (labels paraphrased, quotes copied)."""
    steps = [
        ("n2", "activity", "ADC 自动分类后人工复核", "先走 ADC 自动分，分完还得人过一遍"),
        ("n3", "activity", "值班工程师两小时内初评", "值班工程师两个小时之内要做初评"),
        ("n4", "decision", "是否需要复检", "必须触发复检"),
        ("n5", "activity", "SEM 复判看形貌", "SEM复判看形貌"),
        ("n6", "decision", "复检完是否仍拿不准", "复检完还是拿不准的"),
        ("n7", "approval", "每日工程评审会定处置（48 小时内结论）", "上每天的工程评审会"),
        ("n8", "activity", "所有决策回溯到机台、recipe、批次", "所有决策都要回溯到机台、recipe、批次"),
        ("n9", "activity", "七天内落 CAPA", "七天内把 CAPA 落下去"),
    ]
    nodes = [{"node_id": "n1", "node_type": "start", "label": "扫描完成", "evidence": None}]
    nodes += [{"node_id": i, "node_type": t, "label": label, "actor_roles": [], "evidence": quote}
              for i, t, label, quote in steps]
    nodes.append({"node_id": "n10", "node_type": "end", "label": "闭环完成", "evidence": None})
    chain = ["n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8", "n9", "n10"]
    edges = [{"edge_id": f"e{k}", "from": a, "to": b, "edge_type": "normal"} for k, (a, b) in enumerate(zip(chain, chain[1:]))]
    return {"nodes": nodes, "edges": edges, "start_node_ids": ["n1"], "end_node_ids": ["n10"]}


def test_refreshed_graph_does_not_ask_whether_each_step_was_said(monkeypatch):
    monkeypatch.setattr(guide_service.app_settings, "resolve_slot_for_call",
                        lambda settings, slot: {"enabled": True, "endpoint": "http://x", "model_name": "m"})
    monkeypatch.setattr(llm_client, "chat_completion_json", lambda cfg, messages, timeout=None: _regenerated_response())

    graph = guide_service.regenerate_graph_from_transcript([
        {"role": "assistant", "text": "请您把这件事从开始到结束完整讲一遍。"},
        {"role": "expert", "text": NARRATION},
    ])

    by_id = {n["node_id"]: n for n in graph["nodes"]}
    assert by_id["n5"]["evidence"] == ["SEM复判看形貌"]
    assert all(by_id[i]["evidence"] for i in ("n2", "n3", "n4", "n5", "n6", "n7", "n8", "n9"))
    gaps = review_gaps.rule_gaps(graph, mode="create")
    assert [g for g in gaps if g["kind"] == "unverified_node"] == []


def test_prompt_asks_the_model_for_quotes():
    assert '"evidence"' in guide_service._REGENERATE_SYSTEM_PROMPT
