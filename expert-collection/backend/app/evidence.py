"""Does a quote the model gave as a step's evidence actually come from what the expert said?

Used by both graph builders -- review_agent.extract_from_narrative (「讲完了」) and
guide_service.regenerate_graph_from_transcript (「刷新工作流图」) -- and by the review loop's
edits. A step whose quote can't be matched is asked about first ("您的讲述里我没找到…的原话"),
so a false "not found" turns into a pointless question to the expert.

Matching is on normalized text (punctuation and spaces removed, case folded), per single
expert message:
1. the quote occurs verbatim -- the normal case;
2. otherwise, almost all of its two-character pieces occur in one message, in any order --
   models routinely drop a filler word or join two nearby clauses ("走 SEM 复判，把片子拿去
   看形貌" -> "SEM复判看形貌"), which is still the expert's own wording.
A quote the expert never said shares few pieces with any message and still fails.
"""
from __future__ import annotations

import re

_PUNCT = re.compile(r"[\s，。、；：！？,.;:!?\"“”'‘’（）()《》<>【】\[\]—\-…·]+")

# Share of the quote's two-character pieces that must occur in one expert message, and the
# shortest quote that may be matched this loosely (a 3-character quote has only 2 pieces; one
# coincidence would be half of it).
FUZZY_COVERAGE = 0.8
FUZZY_MIN_CHARS = 4


def norm(text: str) -> str:
    return _PUNCT.sub("", text or "").lower()


def _bigrams(text: str) -> set[str]:
    return {text[i:i + 2] for i in range(len(text) - 1)}


def quote_found(quote: str, sources: list[str]) -> bool:
    q = norm(quote)
    if len(q) < 2:
        return False
    normed = [norm(s) for s in sources]
    if any(q in s for s in normed):
        return True
    if len(q) < FUZZY_MIN_CHARS:
        return False
    pieces = _bigrams(q)
    return any(len(pieces & _bigrams(s)) >= FUZZY_COVERAGE * len(pieces) for s in normed)


def quote_list(quote: object, sources: list[str]) -> list[str]:
    """The node's `evidence` field: the model's quote when it checks out, else [] (unverified).
    Models sometimes return a list of quotes; any one that checks out is enough."""
    quotes = quote if isinstance(quote, list) else [quote]
    return [q.strip() for q in quotes if isinstance(q, str) and quote_found(q, sources)][:3]
