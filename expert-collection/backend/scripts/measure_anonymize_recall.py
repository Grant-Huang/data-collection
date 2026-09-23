"""Recall/precision measurement for app.anonymize.redact_names, against a labeled test set --
IMPLEMENTATION_PLAN.md section 14, §15.2-⑤ acceptance criterion 1: name redaction is
privacy-sensitive, so "it runs without crashing" is not an acceptable bar. Run this once a
real endpoint is configured for the `anonymize_name` slot (see app/settings.py /
IMPLEMENTATION_PLAN.md section 11) to get real numbers -- run against the rule-based fallback
alone (no LLM configured), it mostly demonstrates the metric computation itself, since the
rule-based version's known blind spots (see CASES below) are exactly what it's documented not
to handle.

Usage: python3 scripts/measure_anonymize_recall.py

Each case in CASES is:
- text: the input sentence, written the way an expert might actually phrase it.
- expected_names: substrings that must NOT survive verbatim in the redacted output -- every
  span that should be recognized as a person reference.
- protected: substrings that must survive verbatim -- known false-positive traps (a
  machine/product name that merely contains a common surname, a bare job title with no name
  attached, etc.) that a naive "any name-shaped substring" approach would wrongly redact.

Recall = (expected_names spans no longer present) / (total expected_names spans).
False positives = (protected spans that got mangled) -- reported as a count, since "how many
of N protected spans survived" is more informative here than a single blended rate when N is
small per case.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.anonymize import redact_names  # noqa: E402

CASES: list[dict] = [
    {"text": "是王工发现的，第一时间上报了", "expected_names": ["王工"], "protected": []},
    {"text": "让欧阳工确认一下参数", "expected_names": ["欧阳工"], "protected": []},
    {"text": "李班长和张师傅一起去了现场", "expected_names": ["李班长", "张师傅"], "protected": []},
    {"text": "班组长确认了参数没问题", "expected_names": [], "protected": ["班组长"]},
    {"text": "张三丰机床出现异常报警", "expected_names": [], "protected": ["张三丰机床"]},
    {"text": "王工通知了李班长，李班长又叫上了赵师傅", "expected_names": ["王工", "李班长", "赵师傅"], "protected": []},
    {"text": "陈伟检查了设备状态", "expected_names": ["陈伟"], "protected": []},  # no title suffix, no trailing
                                                                                  # punctuation -- the rule-based
                                                                                  # regex's documented blind spot.
    {"text": "质量工程师复核了报告", "expected_names": [], "protected": ["质量工程师"]},
    {"text": "刘经理和林总监一起做了裁决", "expected_names": ["刘经理", "林总监"], "protected": []},
    {"text": "王氏合金检测结果超标", "expected_names": [], "protected": ["王氏合金"]},
    {"text": "设备维修工程师完成了保养", "expected_names": [], "protected": ["设备维修工程师"]},
    {"text": "马队长带队去了现场，何工做了记录", "expected_names": ["马队长", "何工"], "protected": []},
]


def _contains_verbatim(haystack: str, needle: str) -> bool:
    return needle in haystack


def main() -> None:
    total_expected = 0
    caught = 0
    total_protected = 0
    protected_survived = 0
    used_llm_any = False

    for i, case in enumerate(CASES, 1):
        redacted, count, used_llm = redact_names(case["text"])
        used_llm_any = used_llm_any or used_llm

        case_caught = sum(1 for n in case["expected_names"] if not _contains_verbatim(redacted, n))
        case_missed = [n for n in case["expected_names"] if _contains_verbatim(redacted, n)]
        total_expected += len(case["expected_names"])
        caught += case_caught

        case_protected_ok = sum(1 for p in case["protected"] if _contains_verbatim(redacted, p))
        case_protected_broken = [p for p in case["protected"] if not _contains_verbatim(redacted, p)]
        total_protected += len(case["protected"])
        protected_survived += case_protected_ok

        status = "OK" if not case_missed and not case_protected_broken else "ISSUE"
        print(f"[{i:2}] {status:5} via={'LLM' if used_llm else 'rule'} "
              f"text={case['text']!r} -> redacted={redacted!r}")
        if case_missed:
            print(f"      missed (should have been redacted): {case_missed}")
        if case_protected_broken:
            print(f"      false positive (should NOT have been touched): {case_protected_broken}")

    print()
    recall = caught / total_expected if total_expected else float("nan")
    protected_rate = protected_survived / total_protected if total_protected else float("nan")
    print(f"Recall on expected names:      {caught}/{total_expected} = {recall:.1%}")
    print(f"Protected spans left intact:   {protected_survived}/{total_protected} = {protected_rate:.1%}")
    print(f"Ran via real LLM for any case: {used_llm_any}")
    if not used_llm_any:
        print("(No LLM configured for the anonymize_name slot -- these numbers are the "
              "rule-based fallback's, not a real-model measurement. Configure a real "
              "endpoint and re-run for the actual acceptance numbers.)")


if __name__ == "__main__":
    main()
