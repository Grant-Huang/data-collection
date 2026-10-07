"""Rule-based parsing of the expert's answers to the ontology follow-up questions (design doc
docs/expert-workflow-collection/ontology/MANUFACTURING_OPERATIONAL_ONTOLOGY.md, section 9 /
step 4): "靠什么判断" -> threshold + expected value, "最晚多久" -> ISO 8601 duration.

Same rule as the rest of the interview engine: never invent what the expert didn't say. Only
numbers that literally appear in the answer become structured limits; anything that doesn't
match a simple pattern stays as the verbatim `description` and nothing structured is made up.
"""
from __future__ import annotations

import re
from typing import Any, Optional

_NUM = r"(-?\d+(?:\.\d+)?)"
# Units an expert is likely to say right after a number. Kept verbatim (e.g. "度" is not turned
# into "°C" -- it could be an angle).
_UNIT = r"(°C|℃|度|%|mm|毫米|丝|μm|um|微米|秒|分钟|小时|个|件|N|牛|MPa|bar|转|rpm|V|A|kg|公斤|g|克)?"

_RANGE_RE = re.compile(_NUM + r"\s*" + _UNIT + r"\s*(?:到|至|~|～|-|—)\s*" + _NUM + r"\s*" + _UNIT)
_EXPECTED_RE = re.compile(r"(?:正常|一般|标准|目标|理想|通常)(?:值)?(?:是|在|为|要|应该是|大概|差不多)?\s*" + _NUM + r"\s*" + _UNIT)
_UPPER_RE = re.compile(r"(超过|大于|高于|不能超过|不超过|不大于|不高于|最多|≤|<=|<|＜)\s*" + _NUM + r"\s*" + _UNIT)
_LOWER_RE = re.compile(r"(低于|小于|不低于|不少于|不小于|至少|最少|≥|>=|>|＞)\s*" + _NUM + r"\s*" + _UNIT)

# "超过 X 就……" describes where it stops being OK (a reject band); "不能超过 X" describes the
# acceptable side (normal band's upper bound). Same idea for the lower side.
_UPPER_IS_LIMIT_OF_NORMAL = {"不能超过", "不超过", "不大于", "不高于", "最多", "≤", "<=", "<", "＜"}
_LOWER_IS_LIMIT_OF_NORMAL = {"不低于", "不少于", "不小于", "至少", "最少", "≥", ">="}


def _f(s: str) -> float:
    return float(s)


def parse_criterion_answer(text: str) -> dict[str, Any]:
    """Returns {"limits": [LimitBand dicts], "expected": ExpectedValue dict | None,
    "unit": str | None}. Empty limits / None expected when nothing parseable was said."""
    limits: list[dict[str, Any]] = []
    unit: Optional[str] = None
    expected: Optional[dict[str, Any]] = None

    rng = _RANGE_RE.search(text)
    if rng:
        lo, hi = _f(rng.group(1)), _f(rng.group(3))
        if lo > hi:
            lo, hi = hi, lo
        limits.append({"band": "normal", "lower": lo, "upper": hi})
        unit = rng.group(2) or rng.group(4)

    exp = _EXPECTED_RE.search(text)
    if exp:
        expected = {"target": _f(exp.group(1))}
        unit = unit or exp.group(2)

    for m in _UPPER_RE.finditer(text):
        if rng and rng.start() <= m.start() < rng.end():
            continue  # the "-" of a range is not a bound
        op, val = m.group(1), _f(m.group(2))
        unit = unit or m.group(3)
        if op in _UPPER_IS_LIMIT_OF_NORMAL and not rng:
            limits.append({"band": "normal", "upper": val})
        else:
            limits.append({"band": "reject", "lower": val, "lower_inclusive": False})

    for m in _LOWER_RE.finditer(text):
        op, val = m.group(1), _f(m.group(2))
        unit = unit or m.group(3)
        if op in (">", "＞") and not rng:  # "> X" written as a bound: must be above X
            limits.append({"band": "normal", "lower": val, "lower_inclusive": False})
        elif op in _LOWER_IS_LIMIT_OF_NORMAL and not rng:
            limits.append({"band": "normal", "lower": val})
        else:
            limits.append({"band": "reject", "upper": val, "upper_inclusive": False})

    return {"limits": limits, "expected": expected, "unit": unit}


_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _cn_number(s: str) -> Optional[float]:
    """Small Chinese numerals as experts actually say them: 一..九十九, 两, 半."""
    if s == "半":
        return 0.5
    if re.fullmatch(r"\d+(?:\.\d+)?", s):
        return float(s)
    if not s or any(ch not in _CN_DIGITS and ch != "十" for ch in s):
        return None
    if "十" in s:
        tens, _, ones = s.partition("十")
        return float((_CN_DIGITS.get(tens, 1) if tens else 1) * 10 + (_CN_DIGITS.get(ones, 0) if ones else 0))
    return float(_CN_DIGITS[s]) if len(s) == 1 else None


_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?|[零一二两三四五六七八九十]+|半)\s*(?:个)?\s*(半)?\s*(分钟|分|小时|钟头|天|日|周|星期)")
_ISO_UNIT = {"分钟": ("T", "M", 1), "分": ("T", "M", 1), "小时": ("T", "H", 1), "钟头": ("T", "H", 1),
             "天": ("", "D", 1), "日": ("", "D", 1), "周": ("", "D", 7), "星期": ("", "D", 7)}


def parse_duration(text: str) -> Optional[str]:
    """"4 小时" -> "PT4H", "半小时" -> "PT30M", "三天" -> "P3D", "一个半小时" -> "PT90M".
    Shift-based answers ("一个班") are deliberately not converted -- shift length varies by
    site, so guessing 8 hours would be inventing a number. Returns None when nothing matches."""
    m = _DURATION_RE.search(text)
    if not m:
        return None
    n = _cn_number(m.group(1))
    if n is None:
        return None
    if m.group(2):  # "一个半小时"
        n += 0.5
    t, unit, factor = _ISO_UNIT[m.group(3)]
    n *= factor
    # Fractions go one unit down so the result stays an integer ISO duration.
    if n != int(n):
        if unit == "H":
            n, unit = n * 60, "M"
        elif unit == "D":
            n, unit, t = n * 24, "H", "T"
        else:
            return None
    return f"P{t}{int(n)}{unit}"


# --- Answer -> node patch (shared by the step-by-step guide and the narrate-first review loop)

# A "no" at the start of the answer, allowing spoken filler before it ("这个没有明确的时间要求"
# -- seen in an end-to-end run with a real model), or an explicit "没有…要求/标准" anywhere.
_NEGATIVE_RE = re.compile(
    r"^(?:这个|这|那个|嗯|呃|额|其实|好像|这块|这一步|这里)?[，,、\s]*(?:没有|没|无|不是|不用|不需要|不会|都不|否)"
    r"|没有?(?:什么|明确|具体|固定|硬性)?的?(?:时间|时限|数值|标准|要求)")
# "超时了就找车间主任" / "报给质量经理" -> the role named right after the verb, verbatim.
_ESCALATE_TO_RE = re.compile(r"(?:找|报给|上报给?|通知|升级到|升级给|交给|叫)\s*([^\s，。,；;、！!？?]{2,12})")


def criterion_from_answer(node: dict, text: str) -> Optional[dict[str, Any]]:
    """The evaluation_criteria entry for an answer to "判断时有具体的标准吗", or None when the
    expert declined ("没有，靠经验" -- a "no" that carries no number). "没超过 0.05mm 就行"
    opens like a no but carries a number, so it is an answer."""
    parsed = parse_criterion_answer(text)
    if _NEGATIVE_RE.search(text.strip()) and not parsed["limits"] and not parsed["expected"]:
        return None
    criterion: dict[str, Any] = {
        "id": f"c{len(node.get('evaluation_criteria') or []) + 1}",
        "name": (node.get("decision_question") or node.get("label") or "判断标准")[:40],
        "type": "numeric_range" if parsed["limits"] or parsed["expected"] else "text",
        "description": text,
    }
    if parsed["unit"]:
        criterion["unit"] = parsed["unit"]
    if parsed["limits"]:
        criterion["limits"] = parsed["limits"]
    if parsed["expected"]:
        criterion["expected"] = parsed["expected"]
    return criterion


def sla_from_answer(text: str) -> Optional[dict[str, Any]]:
    """sla_config for an answer to "最晚多久要有结果（超时了会找谁）", or None when the expert
    said there is no time requirement. The escalation target is only filled in when the answer
    names someone after 找/报给/通知…; otherwise it stays unset rather than guessed."""
    duration = parse_duration(text)
    if _NEGATIVE_RE.search(text.strip()) and not duration:
        return None
    sla: dict[str, Any] = {"type": "deadline", "from_trigger": "previous_node_completed", "description": text}
    if duration:
        sla["duration"] = duration
    m = _ESCALATE_TO_RE.search(text)
    if m:
        sla.update({"violation_action": "escalate", "escalate_to_role": m.group(1)})
    return sla
