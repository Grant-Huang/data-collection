"""System Settings endpoints -- PRD 17. See app/settings.py module docstring for what
"saving a config" does and doesn't do yet (assumption 6 in IMPLEMENTATION_PLAN.md), and for
the level-first model config design (IMPLEMENTATION_PLAN.md section 11).
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


@router.post("/llm-levels/{level}/test-connection")
def test_connection(level: str) -> dict:
    """Tests a *level*'s connection, not a slot's -- since every slot pointing at this level
    shares the exact same endpoint/model/key now, there is nothing slot-specific left to
    test (that per-slot redundancy is exactly what the level-first refactor removed).
    """
    settings = settings_module.get_effective_settings()
    if level not in settings["llm_levels"]:
        raise HTTPException(status_code=404, detail="未知的模型级别")
    cfg = settings["llm_levels"][level]
    if not cfg.get("model_name") and not cfg.get("endpoint"):
        return {"ok": False, "message": "尚未填写服务地址或模型名称，请先完善配置再测试。"}
    # Honest limitation (IMPLEMENTATION_PLAN.md assumption 6): this sandbox has no reachable
    # L/C inference service to actually call, so "test connection" cannot report success --
    # doing so would fabricate a result the product explicitly must not fabricate.
    return {"ok": False, "message": "当前环境未配置可达的推理服务，无法真实测试连接（这不代表你填写的配置有误）。"}
