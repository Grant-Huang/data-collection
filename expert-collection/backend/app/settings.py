"""System Settings -- PRD section 17. Real CRUD + persistence; per IMPLEMENTATION_PLAN.md
assumption 6, saving an LLM endpoint here does not actually switch any Mock service's
behavior yet (there's no reachable L/C inference service in this sandbox) -- the page itself
is a real, working configuration surface, only the "takes effect" wiring for LLM calls is
still pending a real model. The quality-parameter and run-parameter sections DO take real
effect (see quality.py's use of get_effective_settings()).
"""
from __future__ import annotations

from typing import Any

from . import db

LLM_SLOTS = [
    "guide_service", "mobile_speech_polish", "experiment_explain",
    "experiment_compare_explain", "error_clustering", "anonymize_name",
    "role_normalize", "dashboard_explain",
]

DEFAULT_SETTINGS: dict[str, Any] = {
    "llm_configs": {
        "guide_service": {"category": "L", "endpoint": "", "model_name": "", "temperature": 0.1, "api_key": ""},
        "mobile_speech_polish": {"category": "L", "enabled": False, "endpoint": "", "model_name": "", "temperature": 0.2, "api_key": ""},
        "experiment_explain": {"category": "C_flagship", "endpoint": "", "model_name": "", "temperature": 0.3, "api_key": ""},
        "experiment_compare_explain": {"category": "C_flagship", "endpoint": "", "model_name": "", "temperature": 0.3, "api_key": ""},
        "error_clustering": {"category": "C_standard", "endpoint": "", "model_name": "", "temperature": 0.2, "api_key": ""},
        "anonymize_name": {"category": "L", "endpoint": "", "model_name": "", "temperature": 0.0, "api_key": ""},
        "role_normalize": {"category": "L", "endpoint": "", "model_name": "", "temperature": 0.0, "api_key": ""},
        "dashboard_explain": {"category": "C_standard", "endpoint": "", "model_name": "", "temperature": 0.2, "api_key": ""},
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

SLOT_LABELS = {
    "guide_service": "专家采集会话引导", "mobile_speech_polish": "移动端语音口述整理",
    "experiment_explain": "实验结果文字解读", "experiment_compare_explain": "多实验对比解读",
    "error_clustering": "Error Analysis 案例聚类归纳", "anonymize_name": "导出匿名化人名脱敏",
    "role_normalize": "角色归一化", "dashboard_explain": "Dashboard 评分项解释生成",
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


def _mask_key(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return "*" * (len(value) - 4) + value[-4:]


def mask_for_display(settings: dict) -> dict:
    """Never echo API keys back in plaintext (PRD 17.2)."""
    masked = {**settings, "llm_configs": {}}
    for slot, cfg in settings.get("llm_configs", {}).items():
        masked["llm_configs"][slot] = {**cfg, "api_key": _mask_key(cfg.get("api_key", "")), "api_key_set": bool(cfg.get("api_key"))}
        del masked["llm_configs"][slot]["api_key"]
    return masked
