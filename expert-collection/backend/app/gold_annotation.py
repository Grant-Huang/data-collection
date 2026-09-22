"""Gold status computation -- IMPLEMENTATION_PLAN.md section 9, §9 Phase C-2. Shared between
routers/annotations.py (per-record status, submission validation) and routers/datasets.py
(the live annotation_readiness dimension, which needs the same status computed across every
record in a version) so the two never compute it differently.
"""
from __future__ import annotations


def compute_gold_status(history: list[dict]) -> str:
    """See IMPLEMENTATION_PLAN.md section 9's four confirmed decisions. Only the first two
    independent annotations (by submission order) decide agreement/disagreement -- a third
    independent annotation isn't part of this design (disagreement goes to arbitration, not a
    running vote), so any independent entries beyond the first two are ignored here (the
    create-annotation endpoint already refuses to accept them).
    """
    independents = [a for a in history if a.get("role_in_process", "independent") == "independent"]
    arbitrations = [a for a in history if a.get("role_in_process") == "arbitration"]
    if arbitrations:
        return "gold" if arbitrations[-1]["verdict"] == "accepted" else "not_gold"
    if len(independents) < 2:
        return "pending_second_review" if independents else "not_gold"
    a, b = independents[0], independents[1]
    if a["verdict"] != b["verdict"]:
        return "disputed_pending_arbitration"
    return "gold" if a["verdict"] == "accepted" else "not_gold"


def cohens_kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Standard two-rater Cohen's kappa over (annotator_1_verdict, annotator_2_verdict)
    pairs -- computed for real (not a placeholder) across every record with two independent
    annotations, regardless of whether it went on to arbitration.
    """
    n = len(pairs)
    if n == 0:
        return None
    po = sum(1 for a, b in pairs if a == b) / n
    categories = {a for a, _ in pairs} | {b for _, b in pairs}
    pe = sum(
        (sum(1 for a, _ in pairs if a == c) / n) * (sum(1 for _, b in pairs if b == c) / n)
        for c in categories
    )
    if pe >= 1.0:
        return 1.0 if po >= 1.0 else 0.0
    return round((po - pe) / (1 - pe), 3)
