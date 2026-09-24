"""Gold status / annotation stage computation -- IMPLEMENTATION_PLAN.md section 9, §9 Phase C-2,
extended with the Rework loop (section 15). Shared between routers/annotations.py
(per-record status, submission validation) and routers/datasets.py (the live
annotation_readiness dimension) so the two never compute it differently.

A record moves through *rounds*. Round 1 reviews the original graph; each Rework submission
(a row in `record_revisions`) produces a corrected graph and opens the next round. Within a
round, the rules are unchanged from Phase C-2: two independent annotations, a third person's
arbitration if they disagree. What changed is what a round's *outcome* means:

- accepted     -> done, Gold
- rejected     -> done, not Gold (discarded)
- needs_revision -> Rework: someone produces the corrected graph, then a new round starts
  (previously this was a dead end: "not Gold" with the suggested fixes never applied).

Stages (what the record is waiting for) drive the annotation queue in the UI:
first_review / second_review / arbitration / rework / done.
"""
from __future__ import annotations

from typing import Optional


def _round_of(a: dict) -> int:
    # Annotations written before rounds existed have no `round` key -- they're round 1.
    return int(a.get("round") or 1)


def _independents(annotations: list[dict]) -> list[dict]:
    return [a for a in annotations if a.get("role_in_process", "independent") == "independent"]


def _arbitrations(annotations: list[dict]) -> list[dict]:
    return [a for a in annotations if a.get("role_in_process") == "arbitration"]


def round_outcome(round_annotations: list[dict]) -> Optional[str]:
    """The verdict a round settled on, or None while it's still open. Only the first two
    independent annotations count (disagreement goes to arbitration, not a running vote).
    """
    arbitrations = _arbitrations(round_annotations)
    if arbitrations:
        return arbitrations[-1]["verdict"]
    independents = _independents(round_annotations)
    if len(independents) >= 2 and independents[0]["verdict"] == independents[1]["verdict"]:
        return independents[0]["verdict"]
    return None


def compute_state(history: list[dict], revisions: list[dict]) -> dict:
    """history: every annotation for the record (any round, oldest first); revisions: every
    rework revision (oldest first). Returns {round, stage, gold_status, outcome,
    round_annotations}.
    """
    current_round = len(revisions) + 1
    in_round = [a for a in history if _round_of(a) == current_round]
    independents = _independents(in_round)
    outcome = round_outcome(in_round)

    if outcome == "accepted":
        stage, gold = "done", "gold"
    elif outcome == "rejected":
        stage, gold = "done", "not_gold"
    elif outcome == "needs_revision":
        stage, gold = "rework", "needs_rework"
    elif len(independents) >= 2:
        stage, gold = "arbitration", "disputed_pending_arbitration"
    elif len(independents) == 1:
        stage, gold = "second_review", "pending_second_review"
    else:
        stage, gold = "first_review", "not_gold"
    return {
        "round": current_round, "stage": stage, "gold_status": gold,
        "outcome": outcome, "round_annotations": in_round,
    }


def compute_gold_status(history: list[dict], revisions: list[dict] | None = None) -> str:
    return compute_state(history, revisions or [])["gold_status"]


def kappa_pairs(history: list[dict]) -> list[tuple[str, str]]:
    """One (first, second) independent-verdict pair per round that has two independent
    annotations -- every such round is a genuine two-rater observation, including rounds that
    later went to arbitration or rework.
    """
    pairs = []
    for r in sorted({_round_of(a) for a in history}):
        ind = _independents([a for a in history if _round_of(a) == r])
        if len(ind) >= 2:
            pairs.append((ind[0]["verdict"], ind[1]["verdict"]))
    return pairs


def cohens_kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Standard two-rater Cohen's kappa over (annotator_1_verdict, annotator_2_verdict)
    pairs -- computed for real (not a placeholder) across every round with two independent
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
