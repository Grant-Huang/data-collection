"""System Settings endpoints -- PRD 17. See app/settings.py module docstring for what
"saving a config" does and doesn't do yet (assumption 6 in IMPLEMENTATION_PLAN.md).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import settings as settings_module

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings() -> dict:
    return settings_module.mask_for_display(settings_module.get_effective_settings())


@router.put("")
def update_settings(patch: dict) -> dict:
    # API key fields: an empty string in the patch means "leave unchanged" (never overwrite
    # a real key with a blank just because the form round-tripped a masked value).
    current = settings_module.get_effective_settings()
    llm_patch = patch.get("llm_configs", {})
    for slot, cfg in llm_patch.items():
        if isinstance(cfg, dict) and cfg.get("api_key") == "":
            cfg.pop("api_key")
        if isinstance(cfg, dict) and slot not in current["llm_configs"]:
            raise HTTPException(status_code=400, detail=f"未知的 LLM 配置项: {slot}")
    merged = settings_module.save_settings(patch)
    return settings_module.mask_for_display(merged)


@router.post("/llm/{slot}/test-connection")
def test_connection(slot: str) -> dict:
    settings = settings_module.get_effective_settings()
    if slot not in settings["llm_configs"]:
        raise HTTPException(status_code=404, detail="未知的配置项")
    cfg = settings["llm_configs"][slot]
    if not cfg.get("model_name") and not cfg.get("endpoint"):
        return {"ok": False, "message": "尚未填写服务地址或模型名称，请先完善配置再测试。"}
    # Honest limitation (IMPLEMENTATION_PLAN.md assumption 6): this sandbox has no reachable
    # L/C inference service to actually call, so "test connection" cannot report success --
    # doing so would fabricate a result the product explicitly must not fabricate.
    return {"ok": False, "message": "当前环境未配置可达的推理服务，无法真实测试连接（这不代表你填写的配置有误）。"}
