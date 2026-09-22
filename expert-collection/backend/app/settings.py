"""System Settings -- PRD section 17. Real CRUD + persistence; per IMPLEMENTATION_PLAN.md
assumption 6, saving an LLM endpoint here does not actually switch any Mock service's
behavior yet (there's no reachable L/C inference service in this sandbox) -- the page itself
is a real, working configuration surface, only the "takes effect" wiring for LLM calls is
still pending a real model. The quality-parameter and run-parameter sections DO take real
effect (see quality.py's use of get_effective_settings()).

Model config is level-first (IMPLEMENTATION_PLAN.md section 11): each of the three model
levels (L / C_standard / C_flagship) is configured exactly once (endpoint, model name, API
key), and each of the 8 usage slots just references which level it uses, plus whatever is
genuinely per-task rather than per-connection (enabled, temperature). Previously every slot
carried its own full endpoint/model_name/api_key, so the same 7B endpoint had to be typed
into 4 different slots' forms and kept in sync by hand -- this is what "重复配置没必要" was
pointing at.
"""
from __future__ import annotations

from typing import Any

from . import db

LEVELS = ["L", "C_standard", "C_flagship"]

LEVEL_LABELS = {
    "L": "L（本地 7B）", "C_standard": "C-标准档", "C_flagship": "C-旗舰档",
}

LLM_SLOTS = [
    "guide_service", "mobile_speech_polish", "experiment_explain",
    "experiment_compare_explain", "error_clustering", "anonymize_name",
    "role_normalize", "dashboard_explain",
]

SLOT_LABELS = {
    "guide_service": "专家采集会话引导", "mobile_speech_polish": "移动端语音口述整理",
    "experiment_explain": "实验结果文字解读", "experiment_compare_explain": "多实验对比解读",
    "error_clustering": "Error Analysis 案例聚类归纳", "anonymize_name": "导出匿名化人名脱敏",
    "role_normalize": "角色归一化", "dashboard_explain": "Dashboard 评分项解释生成",
}

DEFAULT_SETTINGS: dict[str, Any] = {
    "llm_levels": {
        "L": {"endpoint": "", "model_name": "", "api_key": ""},
        "C_standard": {"endpoint": "", "model_name": "", "api_key": ""},
        "C_flagship": {"endpoint": "", "model_name": "", "api_key": ""},
    },
    "llm_slots": {
        "guide_service": {"level": "L", "enabled": True, "temperature": 0.1},
        "mobile_speech_polish": {"level": "L", "enabled": False, "temperature": 0.2},
        "experiment_explain": {"level": "C_flagship", "enabled": True, "temperature": 0.3},
        "experiment_compare_explain": {"level": "C_flagship", "enabled": True, "temperature": 0.3},
        "error_clustering": {"level": "C_standard", "enabled": True, "temperature": 0.2},
        "anonymize_name": {"level": "L", "enabled": True, "temperature": 0.0},
        "role_normalize": {"level": "L", "enabled": True, "temperature": 0.0},
        "dashboard_explain": {"level": "C_standard", "enabled": True, "temperature": 0.2},
    },
    "voice": {"workspace_id": "", "realtime_model": "qwen3-asr-flash-realtime"},
    "quality_params": {
        "min_sample_size": 20,
        "near_dup_text_threshold": 0.85,
        "near_dup_structure_threshold": 0.7,
        "completion_threshold": 80,
        "publish_prompt_count": 20,
        "publish_prompt_days": 14,
    },
    "run_params": {
        "max_concurrent_experiments": 2,
        "run_timeout_seconds": 300,
        "audit_log_retention_days": 90,
        "mobile_session_timeout_minutes": None,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_effective_settings() -> dict:
    stored = db.get_settings()
    return _deep_merge(DEFAULT_SETTINGS, stored) if stored else dict(DEFAULT_SETTINGS)


def save_settings(patch: dict) -> dict:
    current = get_effective_settings()
    merged = _deep_merge(current, patch)
    db.save_settings(merged)
    return merged


def resolve_slot(settings: dict, slot: str) -> dict:
    """A slot's effective model config: the level it points at, joined with whatever the
    slot overrides locally (enabled/temperature). This is what any real LLM call would read
    from -- the level lookup happens once here rather than being duplicated at each call site.
    """
    slot_cfg = settings["llm_slots"][slot]
    level_cfg = settings["llm_levels"][slot_cfg["level"]]
    return {
        "level": slot_cfg["level"],
        "enabled": slot_cfg.get("enabled", True),
        "temperature": slot_cfg.get("temperature", 0.2),
        "endpoint": level_cfg.get("endpoint", ""),
        "model_name": level_cfg.get("model_name", ""),
        "api_key_set": bool(level_cfg.get("api_key")),
    }


def _mask_key(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return "*" * (len(value) - 4) + value[-4:]


def mask_for_display(settings: dict) -> dict:
    """Never echo API keys back in plaintext (PRD 17.2). Only llm_levels carry a key now --
    llm_slots have nothing secret in them (level reference + enabled + temperature).
    """
    masked = {**settings, "llm_levels": {}}
    for level, cfg in settings.get("llm_levels", {}).items():
        masked["llm_levels"][level] = {
            **cfg, "api_key": _mask_key(cfg.get("api_key", "")), "api_key_set": bool(cfg.get("api_key")),
        }
        del masked["llm_levels"][level]["api_key"]
    return masked
