"""Export transforms -- PRD 12.3/12.4, Phase 6 sub-scope (IMPLEMENTATION_PLAN.md section 8).

role_normalized: pure rule/dictionary mapping, no LLM needed (PRD 12.4).

anonymized: the expert_id_hash/experience-year bucketing rules are real rule-based
implementations. Name redaction is the one piece PRD 12.4/15.2 says explicitly needs an LLM
for acceptable recall (IMPLEMENTATION_PLAN.md section 14, §15.2-⑤) -- `redact_names` now
calls the real model through the `anonymize_name` slot when configured, with the regex +
surname-dictionary version kept as the fallback for when it isn't (or the model's output
fails the safety check below), not a claim of LLM-level recall on its own.

Safety check on the LLM path: the model is only ever supposed to *delete* name spans and
replace them with "某人", never rewrite, summarize, or add anything else to the text -- so
`_is_subsequence` verifies that the redacted text, with every "某人" removed, is still a
subsequence of the original (same characters, same order, nothing invented). Any output that
fails this is rejected and the rule-based fallback runs instead, exactly like an LLM error.
This module makes no recall/precision claim about the LLM path by itself; see
scripts/measure_anonymize_recall.py for the labeled test set this needs to be run against
once a real endpoint is configured (IMPLEMENTATION_PLAN.md section 14 acceptance criterion 1).
"""
from __future__ import annotations

import re

from . import llm_client
from . import settings as app_settings

# A small, illustrative surname dictionary -- not exhaustive. Real coverage needs the LLM
# step PRD 12.4 calls for; this is the documented rule-based fallback, not a replacement.
COMMON_SURNAMES = [
    "王", "李", "张", "刘", "陈", "杨", "黄", "赵", "周", "吴",
    "徐", "孙", "马", "朱", "胡", "郭", "何", "高", "林", "郑",
]

TITLE_SUFFIXES = ["工", "师", "主管", "组长", "经理", "总监", "班长", "队长"]

_NAME_PATTERN = re.compile(
    "(" + "|".join(COMMON_SURNAMES) + ")[一-龥]{1,2}(?=" + "|".join(TITLE_SUFFIXES) + "|[，,。.\\s]|$)"
)

ROLE_SYNONYMS: dict[str, str] = {
    "质检": "质量工程师", "QE": "质量工程师", "质量员": "质量工程师", "质检员": "质量工程师",
    "班长": "班组长", "组长": "班组长",
    "维修工": "设备维修工程师", "维修师傅": "设备维修工程师",
    "工艺员": "工艺工程师", "工艺师": "工艺工程师",
}


def normalize_role(raw: str) -> str:
    return ROLE_SYNONYMS.get(raw.strip(), raw.strip())


def _rule_based_redact_names(text: str) -> tuple[str, int]:
    """The documented rule-based fallback -- see module docstring."""
    count = 0

    def _replace(match: re.Match) -> str:
        nonlocal count
        count += 1
        return "某人"

    redacted = _NAME_PATTERN.sub(_replace, text)
    return redacted, count


_REDACT_SYSTEM_PROMPT = """你是制造业专家访谈记录的人名脱敏助手。找出文本里指代具体某个人的人名（可能带姓氏+职务称呼，比如"王工""李师傅""张班长"，也可能是纯人名），把每一处替换成"某人"，除此之外一个字都不要改动——不能改写、不能总结、不能删除或添加任何其他内容，只做"人名 -> 某人"这一种替换。

只输出一个 JSON object，字段：
- "redacted_text"：替换后的完整文本。
- "count"：替换了几处。

只输出 JSON，不要有任何其他文字。"""


def _is_subsequence(needle: str, haystack: str) -> bool:
    it = iter(haystack)
    return all(ch in it for ch in needle)


def _llm_redact_names(text: str, slot_config: dict) -> tuple[str, int] | None:
    """Returns None (caller falls back to the rule-based path) on any failure: not
    configured, LLM call error, malformed output, or output that fails the
    "only deletions, nothing added or reworded" subsequence check.
    """
    try:
        parsed = llm_client.chat_completion_json(slot_config, [
            {"role": "system", "content": _REDACT_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ])
    except llm_client.LLMError:
        return None
    redacted_text = parsed.get("redacted_text")
    if not isinstance(redacted_text, str):
        return None
    stripped = redacted_text.replace("某人", "")
    if not _is_subsequence(stripped, text):
        return None
    return redacted_text, redacted_text.count("某人")


def redact_names(text: str) -> tuple[str, int, bool]:
    """Returns (redacted_text, redaction_count, used_llm). Prefers the real LLM (via the
    `anonymize_name` slot) when configured; falls back to the rule-based surname-dictionary
    version on any failure -- see module docstring. `used_llm` reflects what actually
    happened on this call, not just whether the slot is nominally configured, so a caller
    aggregating over many calls (apply_anonymization below) can honestly report whether
    every redaction in the export actually went through the model or some fell back.
    """
    slot_config = app_settings.resolve_slot_for_call(app_settings.get_effective_settings(), "anonymize_name")
    if slot_config.get("enabled") and slot_config.get("endpoint") and slot_config.get("model_name"):
        result = _llm_redact_names(text, slot_config)
        if result is not None:
            return result[0], result[1], True
    text, count = _rule_based_redact_names(text)
    return text, count, False


def bucket_experience_years(years: int) -> str:
    if years >= 30:
        return "30年以上"
    if years >= 20:
        return "20-30年"
    if years >= 10:
        return "10-20年"
    if years >= 5:
        return "5-10年"
    return "5年以下"


def apply_role_normalization(graph: dict) -> dict:
    graph = {**graph, "nodes": [
        {**n, "actor_roles": [normalize_role(r) for r in n.get("actor_roles", [])]}
        for n in graph.get("nodes", [])
    ]}
    return graph


def apply_anonymization(record: dict) -> dict:
    """record: a workflow record dict (expert_collected shape or public_extracted shape).
    Returns a deep-ish copy with anonymization rules applied.
    """
    record = dict(record)
    graph = record.get("graph", {})
    total_redactions = 0
    any_llm = False
    any_fallback = False

    new_nodes = []
    for n in graph.get("nodes", []):
        label, count, used_llm = redact_names(n.get("label", ""))
        total_redactions += count
        any_llm = any_llm or used_llm
        any_fallback = any_fallback or not used_llm
        new_nodes.append({**n, "label": label, "actor_roles": [normalize_role(r) for r in n.get("actor_roles", [])]})
    record["graph"] = {**graph, "nodes": new_nodes}

    provenance = record.get("provenance")
    if provenance and provenance.get("expert_years_experience") is not None:
        provenance = {**provenance, "expert_years_experience": bucket_experience_years(provenance["expert_years_experience"])}
        record["provenance"] = provenance

    if any_llm and not any_fallback:
        method_note = "人名脱敏使用真实模型识别（`anonymize_name` 环节）"
    elif any_llm and any_fallback:
        method_note = "人名脱敏部分使用真实模型识别、部分因调用失败退回规则兜底（姓氏词典 + 称呼模式）"
    else:
        method_note = "人名脱敏为规则兜底（姓氏词典 + 称呼模式），召回率有限，不等同于 PRD 12.4/15.2 要求的 LLM 语义识别效果"
    record["_anonymization_note"] = f"{method_note}，本次替换 {total_redactions} 处。"
    return record
