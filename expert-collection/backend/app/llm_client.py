"""OpenAI-compatible LLM client -- IMPLEMENTATION_PLAN.md section 14, §15.1-①(a). Thin
wrapper every real-LLM slot (guide_service first, explain.py/anonymize.py/error_clustering
later) calls through, so the HTTP plumbing and error handling exist in exactly one place
instead of being reimplemented per slot.

Honesty about failure handling: a real inference service can time out, return a non-2xx
status, or hand back a response that isn't valid JSON / doesn't have the expected shape.
None of these should ever crash the caller or hang the request -- they all come back as an
`LLMError` with a `kind` the caller can branch on (retry once, fall back to a rule-based
path, or surface "AI 服务暂时不可用" to the expert). This module never silently swallows a
failure into an empty string or a fabricated success.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 20.0


class LLMError(Exception):
    """`kind` is one of "not_configured" | "timeout" | "http_error" | "bad_response", so
    callers can decide how to degrade without parsing the message text.
    """

    def __init__(self, kind: str, message: str):
        self.kind = kind
        super().__init__(message)


@dataclass
class LLMResult:
    content: str
    raw: dict[str, Any]


def _post_chat_completion(url: str, api_key: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
    """One HTTP round trip: POST `body`, return the parsed JSON response. Raises `LLMError`
    on any failure. Split out of `chat_completion` so it can be retried with a slightly
    different body (see the `chat_template_kwargs` retry below) without duplicating the
    request/response plumbing.
    """
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {api_key}"} if api_key else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_bytes = resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        raise LLMError("http_error", f"推理服务返回 {e.code}：{detail}") from e
    except TimeoutError as e:
        raise LLMError("timeout", f"推理服务请求超时（>{timeout}s）") from e
    except urllib.error.URLError as e:
        raise LLMError("timeout", f"无法连接推理服务：{e.reason}") from e

    try:
        return json.loads(raw_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise LLMError("bad_response", "推理服务返回的不是合法 JSON") from e


def chat_completion(slot_config: dict, messages: list[dict[str, str]], *,
                     timeout: float = DEFAULT_TIMEOUT_SECONDS,
                     response_format_json: bool = False) -> LLMResult:
    """`slot_config` is `settings.resolve_slot_for_call()`'s output for one slot. Raises
    `LLMError` on any failure -- this function never returns a fabricated fallback on its
    own; deciding what to do about a failure is the caller's job, per slot.
    """
    endpoint = (slot_config.get("endpoint") or "").strip()
    api_key = slot_config.get("api_key") or ""
    model_name = (slot_config.get("model_name") or "").strip()
    if not endpoint or not model_name:
        raise LLMError("not_configured", "该环节未配置可达的推理服务（endpoint/model_name 为空）")

    url = endpoint.rstrip("/") + "/chat/completions"
    body: dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "temperature": slot_config.get("temperature", 0.2),
        # Disable Qwen3 thinking mode by default. Server-side --reasoning-budget 0 does
        # not propagate through llama.cpp's jinja template; the only way to actually skip
        # the `<think>...</think>` block is via chat_template_kwargs. Without this, 35B
        # burns every max_tokens on reasoning_content and finishes with empty JSON.
        # Slots that genuinely want thinking (none today) can override by passing their
        # own chat_template_kwargs through a future slot-level config knob.
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if response_format_json:
        body["response_format"] = {"type": "json_object"}

    try:
        parsed = _post_chat_completion(url, api_key, body, timeout)
    except LLMError as e:
        # chat_template_kwargs is a llama.cpp/vLLM extension, not part of the OpenAI Chat
        # Completions schema -- a strict OpenAI-compatible endpoint (e.g. a level pointed at
        # a real cloud vendor instead of the local Qwen3 server) can reject the whole request
        # over this one unrecognized field. Rather than let that silently break every call
        # to that level, retry once without it before giving up, and log it so ops can see
        # a level's endpoint doesn't tolerate this field instead of it just "not working".
        if e.kind == "http_error" and "chat_template_kwargs" in body:
            logger.warning(
                "chat_completion: %s rejected chat_template_kwargs (%s); retrying once without it",
                url, e,
            )
            retry_body = {k: v for k, v in body.items() if k != "chat_template_kwargs"}
            parsed = _post_chat_completion(url, api_key, retry_body, timeout)
        else:
            raise

    try:
        content = parsed["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(
            "bad_response",
            f"推理服务响应缺少 choices[0].message.content 字段：{parsed!r}"[:500],
        ) from e

    if not isinstance(content, str):
        raise LLMError("bad_response", "推理服务响应的 content 字段不是字符串")

    return LLMResult(content=content, raw=parsed)


def chat_completion_json(slot_config: dict, messages: list[dict[str, str]], *,
                          timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Same as `chat_completion`, but additionally requires the content itself to parse as a
    JSON object -- asks the server for `response_format: json_object` and then verifies it
    actually got a JSON object back. For slots like guide_service that need structured
    output (graph ops), not free-form prose.
    """
    result = chat_completion(slot_config, messages, timeout=timeout, response_format_json=True)
    try:
        parsed_content = json.loads(result.content)
    except json.JSONDecodeError as e:
        raise LLMError("bad_response", f"模型输出不是合法 JSON：{result.content[:300]!r}") from e
    if not isinstance(parsed_content, dict):
        raise LLMError("bad_response", "模型输出的 JSON 不是一个 object")
    return parsed_content
