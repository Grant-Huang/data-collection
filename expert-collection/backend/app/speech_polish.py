"""Voice icon ① ("专家原话经过大模型整理以后进入输入框"): turns a raw ASR transcript (browser
SpeechRecognition output -- run-on, no punctuation, filled with spoken-language fillers) into
a cleaner draft the expert can still review/edit before sending. Wires the `mobile_speech_polish`
slot that app/settings.py has carried since Phase 1 with no real call site ("移动端语音口述整理").

Same fallback contract as guide_service.py's `_understand_step`: never raises, never blocks the
input box on a slow/broken inference service -- any failure (not configured, disabled, timeout,
bad output) falls back to returning the raw transcript untouched, `polished=False`, so the
expert always ends up with *something* in the input box, never an error swallowed into silence.
"""
from __future__ import annotations

from . import llm_client
from . import settings as app_settings

_POLISH_SYSTEM_PROMPT = """你是一个帮制造业专家把口述内容整理成书面文字的助手。输入是语音识别的原始文本（可能没有标点、有口头禅、重复、语序混乱），你要输出整理后的书面化文字：

- 补上合理的标点符号，分段/分句清晰。
- 去掉明显的口头禅和重复（"呃""就是说""对对对"之类），但不要改变专家表达的实际意思。
- 不要替专家总结、缩写或添加原文没有的信息，只是把口语整理成书面语。
- 保留专家的专业术语、人名、编号等原样，不要"纠正"成你以为对的说法。

只输出整理后的文字本身，不要有任何解释、引号或额外内容。"""


def _llm_polish(text: str, slot_config: dict) -> str | None:
    """Returns None on ANY failure so the caller falls back to the raw transcript -- mirrors
    guide_service.py's `_llm_understand_step` contract.
    """
    try:
        result = llm_client.chat_completion(slot_config, [
            {"role": "system", "content": _POLISH_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ])
    except llm_client.LLMError:
        return None
    polished = result.content.strip()
    return polished or None


def polish_transcript(text: str) -> tuple[str, bool]:
    """The one entry point voice input goes through to turn a raw transcript into what fills
    the input box. Returns (text_to_use, polished).
    """
    raw = text.strip()
    if not raw:
        return raw, False

    slot_config = app_settings.resolve_slot_for_call(app_settings.get_effective_settings(), "mobile_speech_polish")
    if slot_config.get("enabled") and slot_config.get("endpoint") and slot_config.get("model_name"):
        polished = _llm_polish(raw, slot_config)
        if polished is not None:
            return polished, True
    return raw, False
