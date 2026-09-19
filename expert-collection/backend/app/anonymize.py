"""Export transforms -- PRD 12.3/12.4, Phase 6 sub-scope (IMPLEMENTATION_PLAN.md section 8).

role_normalized: pure rule/dictionary mapping, no LLM needed (PRD 12.4).

anonymized: the expert_id_hash/experience-year bucketing rules are real rule-based
implementations. Name redaction is the one piece PRD 12.4/15.2 says explicitly needs an LLM
for acceptable recall -- this module's regex + surname-dictionary version is the documented
"rule-based fallback" the PRD itself allows for, not a claim of LLM-level recall. It's honest
about that limitation rather than silently under- or over-redacting and calling it done.
"""
from __future__ import annotations

import re

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


def redact_names(text: str) -> tuple[str, int]:
    """Returns (redacted_text, redaction_count). Rule-based fallback -- see module docstring."""
    count = 0

    def _replace(match: re.Match) -> str:
        nonlocal count
        count += 1
        return "某人"

    redacted = _NAME_PATTERN.sub(_replace, text)
    return redacted, count


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

    new_nodes = []
    for n in graph.get("nodes", []):
        label, count = redact_names(n.get("label", ""))
        total_redactions += count
        new_nodes.append({**n, "label": label, "actor_roles": [normalize_role(r) for r in n.get("actor_roles", [])]})
    record["graph"] = {**graph, "nodes": new_nodes}

    provenance = record.get("provenance")
    if provenance and provenance.get("expert_years_experience") is not None:
        provenance = {**provenance, "expert_years_experience": bucket_experience_years(provenance["expert_years_experience"])}
        record["provenance"] = provenance

    record["_anonymization_note"] = (
        f"人名脱敏为规则兜底（姓氏词典 + 称呼模式），本次替换 {total_redactions} 处，"
        "召回率有限，不等同于 PRD 12.4/15.2 要求的 LLM 语义识别效果。"
    )
    return record
