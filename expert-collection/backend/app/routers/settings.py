"""System Settings endpoints -- PRD 17. See app/settings.py module docstring for what
"saving a config" does and doesn't do yet (assumption 6 in IMPLEMENTATION_PLAN.md), and for
the level-first model config design (IMPLEMENTATION_PLAN.md section 11).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import llm_client, settings as settings_module

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Kept short and cheap on purpose -- this is a connectivity probe the person configuring a
# level clicks and waits on synchronously, not a real generation call. Just needs a live
# choices[0].message.content back, not a long or good answer.
_TEST_CONNECTION_TIMEOUT_SECONDS = 10.0
_TEST_CONNECTION_MESSAGES = [
    {"role": "user", "content": "请只回复\"ok\"两个字，用于测试连接是否正常。"},
]


@router.get("")
def get_settings() -> dict:
    return settings_module.mask_for_display(settings_module.get_effective_settings())


@router.put("")
def update_settings(patch: dict) -> dict:
    current = settings_module.get_effective_settings()

    # API key fields: an empty string in the patch means "leave unchanged" (never overwrite
    # a real key with a blank just because the form round-tripped a masked value).
    level_patch = patch.get("llm_levels", {})
    for level, cfg in level_patch.items():
        if level not in current["llm_levels"]:
            raise HTTPException(status_code=400, detail=f"未知的模型级别: {level}")
        if isinstance(cfg, dict) and cfg.get("api_key") == "":
            cfg.pop("api_key")

    slot_patch = patch.get("llm_slots", {})
    for slot, cfg in slot_patch.items():
        if slot not in current["llm_slots"]:
            raise HTTPException(status_code=400, detail=f"未知的环节: {slot}")
        if isinstance(cfg, dict) and "level" in cfg and cfg["level"] not in current["llm_levels"]:
            raise HTTPException(status_code=400, detail=f"未知的模型级别: {cfg['level']}")

    merged = settings_module.save_settings(patch)
    return settings_module.mask_for_display(merged)


_LLM_ERROR_MESSAGES = {
    "not_configured": "尚未填写服务地址或模型名称，请先完善配置再测试。",
    "timeout": "无法连接到该服务地址（超时或拒绝连接），请检查 endpoint 是否可达、网络/防火墙是否放行。",
    "http_error": "服务地址可达，但返回了错误状态码，请检查 model_name / api_key 是否正确。",
    "bad_response": "服务地址可达，但响应内容不是预期的 OpenAI 兼容格式，请确认该服务实现了 /chat/completions 接口。",
}


@router.post("/llm-levels/{level}/test-connection")
def test_connection(level: str) -> dict:
    """Tests a *level*'s connection, not a slot's -- since every slot pointing at this level
    shares the exact same endpoint/model/key now, there is nothing slot-specific left to
    test (that per-slot redundancy is exactly what the level-first refactor removed).

    This actually calls the configured endpoint (via llm_client, the same OpenAI-compatible
    client every real LLM slot uses) rather than reporting a canned result: IMPLEMENTATION_PLAN.md
    assumption 6's "沙箱没有可达的推理服务" was true for THIS session's sandbox, not for every
    environment the product runs in -- once deployed somewhere with a real reachable L/C
    service, refusing to actually try the call would be dishonest in the other direction
    (claiming a working feature can't do the one thing it's for). Success/failure is still
    never fabricated: this reports exactly what llm_client got back, nothing guessed.
    """
    settings = settings_module.get_effective_settings()
    if level not in settings["llm_levels"]:
        raise HTTPException(status_code=404, detail="未知的模型级别")
    slot_config = {**settings["llm_levels"][level], "temperature": 0.0}
    try:
        result = llm_client.chat_completion(
            slot_config, _TEST_CONNECTION_MESSAGES, timeout=_TEST_CONNECTION_TIMEOUT_SECONDS,
        )
    except llm_client.LLMError as e:
        return {"ok": False, "message": f"{_LLM_ERROR_MESSAGES.get(e.kind, str(e))}（{e}）"}
    preview = result.content.strip()[:80]
    return {"ok": True, "message": f"连接成功，模型回复：{preview!r}"}
