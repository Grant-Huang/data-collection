"""System Settings -- PRD section 17. Real CRUD + persistence, and (per IMPLEMENTATION_PLAN.md
section 14) saving an LLM endpoint here DOES take effect for every slot that has been wired to
a real model (guide_service, experiment_explain/compare_explain, dashboard_explain,
error_clustering, anonymize_name -- see resolve_slot_for_call() and each slot's own module for
its rule-based fallback on any failure). The remaining slots (mobile_speech_polish,
role_normalize) still have no real-LLM call site regardless of what's configured here.
IMPLEMENTATION_PLAN.md assumption 6 ("no reachable L/C inference service") described the
development sandbox this was built in, not every environment the product runs in -- once
pointed at a real reachable endpoint (including in production), it is actually called.

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
    "role_normalize", "dashboard_explain", "graph_regenerate",
]

SLOT_LABELS = {
    "guide_service": "专家采集会话引导", "mobile_speech_polish": "移动端语音口述整理",
    "experiment_explain": "实验结果文字解读", "experiment_compare_explain": "多实验对比解读",
    "error_clustering": "Error Analysis 案例聚类归纳", "anonymize_name": "导出匿名化人名脱敏",
    "role_normalize": "角色归一化", "dashboard_explain": "Dashboard 评分项解释生成",
    "graph_regenerate": "根据会话内容重新生成流程图",
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
        # Whole-transcript -> whole-DAG in one call is a much bigger structured-output task
        # than guide_service's one-sentence parse, so it defaults to C_standard, not L.
        "graph_regenerate": {"level": "C_standard", "enabled": True, "temperature": 0.1},
    },
    "voice": {"workspace_id": "", "realtime_model": "qwen3-asr-flash-realtime", "api_key": ""},
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


def resolve_slot_for_call(settings: dict, slot: str) -> dict:
    """Same join as `resolve_slot`, but with the real `api_key` value instead of the masked
    `api_key_set` boolean -- this is what `llm_client.py` reads to actually make a call. Never
    return this dict from an API response; `resolve_slot`/`mask_for_display` exist precisely
    so the settings endpoints don't have to handle masking themselves.
    """
    slot_cfg = settings["llm_slots"][slot]
    level_cfg = settings["llm_levels"][slot_cfg["level"]]
    return {
        "level": slot_cfg["level"],
        "enabled": slot_cfg.get("enabled", True),
        "temperature": slot_cfg.get("temperature", 0.2),
        "endpoint": level_cfg.get("endpoint", ""),
        "model_name": level_cfg.get("model_name", ""),
        "api_key": level_cfg.get("api_key", ""),
    }


def _mask_key(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return "*" * (len(value) - 4) + value[-4:]


def mask_for_display(settings: dict) -> dict:
    """Never echo secrets back in plaintext (PRD 17.2): API keys for every llm_level and the
    voice service, plus the "L" level's endpoint -- for a local model that's a filesystem
    path/internal address, not something that should show up in plaintext on screen either.
    C_standard/C_flagship's endpoint is a public API URL, not a local path, so it's left as-is.
    """
    masked = {**settings, "llm_levels": {}}
    for level, cfg in settings.get("llm_levels", {}).items():
        level_out = {
            **cfg, "api_key": _mask_key(cfg.get("api_key", "")), "api_key_set": bool(cfg.get("api_key")),
        }
        del level_out["api_key"]
        if level == "L":
            # Fully hidden, not partially revealed like _mask_key does for API keys: a local
            # file path's tail characters (extension, folder name) are still identifying
            # information, and the frontend only needs the boolean to decide what to show.
            level_out["endpoint"] = ""
            level_out["endpoint_set"] = bool(cfg.get("endpoint"))
        masked["llm_levels"][level] = level_out

    voice = dict(settings.get("voice", {}))
    voice["api_key_set"] = bool(voice.get("api_key"))
    voice.pop("api_key", None)
    masked["voice"] = voice

    return masked
