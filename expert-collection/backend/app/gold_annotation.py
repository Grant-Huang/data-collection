"""Gold status / annotation stage computation -- IMPLEMENTATION_PLAN.md section 9, §9 Phase C-2,
extended with the Rework loop (section 16). Shared between routers/annotations.py
(per-record status, submission validation) and routers/datasets.py (the live
annotation_readiness dimension) so the two never compute it differently.

Within a round the rules are unchanged from Phase C-2: two independent annotations, a third
person's arbitration if they disagree. Outcomes (section 17):

- accepted       -> done, Gold (the record's graph as is)
- rejected       -> done, not Gold (discarded)
- needs_revision -> done, Gold with the corrected graph -- when both annotators produced the
  same correction, or the arbitrator picked / made one.

Rounds only exist for legacy data: section 16's rework submissions (rows in
`record_revisions`) each opened a new round on the corrected graph. Section 17 creates no new
revisions, so current records stay in round 1 (or whatever round their legacy data reached).

Stages (what the record is waiting for) drive the annotation queue in the UI:
first_review / second_review / arbitration / done. Section 17 removed the separate rework
stage: annotators correct the graph in the review conversation, so a "needs_revision"
annotation carries its corrected graph and the round settles directly (see round_decision).
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
    """Section 16 semantics, kept for counting *past* rounds of legacy data (rounds that ended
    in a rework revision): the verdict a round settled on by arbitration or agreement."""
    arbitrations = _arbitrations(round_annotations)
    if arbitrations:
        return arbitrations[-1]["verdict"]
    independents = _independents(round_annotations)
    if len(independents) >= 2 and independents[0]["verdict"] == independents[1]["verdict"]:
        return independents[0]["verdict"]
    return None


def _settles(a: dict) -> bool:
    # "needs_revision" only settles a record when it comes with the corrected graph (section
    # 17: annotators correct the graph in conversation). Legacy section-16 annotations have
    # no revised_graph, so they never settle on their own.
    return a["verdict"] != "needs_revision" or bool(a.get("revised_graph"))


def round_decision(round_annotations: list[dict]) -> Optional[dict]:
    """How the current round was decided, or None if it still needs someone:
    {"verdict", "graph" (corrected graph for needs_revision, else None), "annotation"}.
    - a settling arbitration decides;
    - otherwise two independent annotations that agree decide -- for needs_revision only if
      both corrected graphs are structurally identical (graph_signature);
    - anything else (disagreement, two different corrections, legacy corrections without a
      graph) goes to arbitration."""
    arbs = [a for a in _arbitrations(round_annotations) if _settles(a)]
    if arbs:
        a = arbs[-1]
        return {"verdict": a["verdict"], "graph": a.get("revised_graph") if a["verdict"] == "needs_revision" else None, "annotation": a}
    ind = _independents(round_annotations)[:2]
    if len(ind) == 2 and ind[0]["verdict"] == ind[1]["verdict"]:
        v = ind[0]["verdict"]
        if v != "needs_revision":
            return {"verdict": v, "graph": None, "annotation": ind[0]}
        g0, g1 = ind[0].get("revised_graph"), ind[1].get("revised_graph")
        if g0 and g1 and graph_signature(g0) == graph_signature(g1):
            return {"verdict": v, "graph": g0, "annotation": ind[0]}
    return None


def compute_state(history: list[dict], revisions: list[dict]) -> dict:
    """history: every annotation for the record (oldest first); revisions: legacy section-16
    rework revisions (each opened a new round; section 17 creates none). Returns
    {round, stage, gold_status, outcome, final_graph, round_annotations}. `final_graph` is
    the corrected graph when the record settled on needs_revision, else None (= the
    record's current graph)."""
    current_round = len(revisions) + 1
    in_round = [a for a in history if _round_of(a) == current_round]
    independents = _independents(in_round)
    decision = round_decision(in_round)

    if decision:
        stage = "done"
        gold = "not_gold" if decision["verdict"] == "rejected" else "gold"
    elif len(independents) >= 2:
        stage, gold = "arbitration", "disputed_pending_arbitration"
    elif len(independents) == 1:
        stage, gold = "second_review", "pending_second_review"
    else:
        stage, gold = "first_review", "not_gold"
    return {
        "round": current_round, "stage": stage, "gold_status": gold,
        "outcome": decision["verdict"] if decision else None,
        "final_graph": decision["graph"] if decision else None,
        "round_annotations": in_round,
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


def graph_signature(graph: dict | None) -> tuple:
    """Id-independent structural fingerprint: two annotators who independently make the same
    correction get different node ids for new steps, so graphs are compared by step labels,
    types, actors, connections and conditions instead (section 17.4)."""
    if not graph:
        return ()
    label = {n["node_id"]: n.get("label", "").strip() for n in graph.get("nodes", [])}
    nodes = sorted((n.get("label", "").strip(), n.get("node_type"), tuple(sorted(n.get("actor_roles") or [])),
                    bool((n.get("retry_semantics") or {}).get("enabled"))) for n in graph.get("nodes", []))
    edges = sorted((label.get(e["from"], e["from"]), label.get(e["to"], e["to"]), e.get("edge_type"),
                    (e.get("condition") or "").strip()) for e in graph.get("edges", []))
    return (tuple(nodes), tuple(edges))
