"""C6: a fast LLM failure is retried once; a slow one (timeout) or a missing config is not."""
import json

import pytest

from app import llm_client

CFG = {"endpoint": "http://x", "model_name": "m", "api_key": ""}
OK = {"choices": [{"message": {"content": json.dumps({"ok": True})}}]}


def _server(monkeypatch, replies):
    calls = []

    def fake(url, api_key, body, timeout):
        calls.append(body)
        r = replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(llm_client, "_post_chat_completion", fake)
    return calls


def test_fast_failure_is_retried_once(monkeypatch):
    calls = _server(monkeypatch, [llm_client.LLMError("timeout", "无法连接推理服务"), OK])
    assert llm_client.chat_completion_json(CFG, [{"role": "user", "content": "hi"}]) == {"ok": True}
    assert len(calls) == 2


def test_malformed_reply_is_retried_once(monkeypatch):
    bad = {"choices": [{"message": {"content": "不是 JSON"}}]}
    calls = _server(monkeypatch, [bad, OK])
    assert llm_client.chat_completion_json(CFG, [{"role": "user", "content": "hi"}]) == {"ok": True}
    assert len(calls) == 2


def test_second_failure_is_raised(monkeypatch):
    calls = _server(monkeypatch, [llm_client.LLMError("http_error", "502"), llm_client.LLMError("http_error", "502")] * 2)
    with pytest.raises(llm_client.LLMError):
        llm_client.chat_completion_json(CFG, [{"role": "user", "content": "hi"}])
    # Each attempt may itself retry once without chat_template_kwargs on an http_error.
    assert len(calls) == 4


def test_slow_failure_is_not_retried(monkeypatch):
    calls = _server(monkeypatch, [llm_client.LLMError("timeout", "超时"), OK])
    clock = iter([0.0, llm_client.FAST_FAILURE_SECONDS + 1])
    monkeypatch.setattr(llm_client.time, "monotonic", lambda: next(clock))
    with pytest.raises(llm_client.LLMError):
        llm_client.chat_completion_json(CFG, [{"role": "user", "content": "hi"}])
    assert len(calls) == 1


def test_not_configured_is_not_retried(monkeypatch):
    calls = _server(monkeypatch, [OK])
    with pytest.raises(llm_client.LLMError):
        llm_client.chat_completion_json({"endpoint": "", "model_name": ""}, [{"role": "user", "content": "hi"}])
    assert calls == []
