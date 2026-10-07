"""Clarification list for the review loop (IMPLEMENTATION_PLAN.md section 17.3).

Rule-based and deterministic: what's worth asking about a graph, in priority order. The model
only picks among / phrases these (plus uncertainties it flags itself), so "what to ask"
stays reproducible and testable -- the same division of labour section 15's planner used.

A gap is a dict:
    {"id", "kind", "priority", "text", "node_ids", "status", "source"}
- `id` is deterministic (kind + node ids) so recomputing after every edit keeps statuses.
- `status`: open -> asked (the agent asked it; never asked twice) -> resolved / dismissed.
- `source`: "rule" (recomputed each turn; a rule gap that no longer applies resolves itself)
  or "model" (an uncertainty the model flagged; stays until resolved or asked).
Lower `priority` is asked first.
"""
from __future__ import annotations

import hashlib
from typing import Iterable

from . import graph_validator

# Coverage checks: asked once each when the narration didn't already produce that structure.
# Wording avoids jargon (分支/并行/节点), same rule as guide_phrasing's validation.
COVERAGE_QUESTIONS = {
    "exceptions": "整个过程里有没有例外情况，会走不一样的处理？比如检查不合格、找不到人、缺料的时候。",
    "parallel": "这些步骤里，有没有哪几件事是同时进行的？",
    "approval": "中间有没有哪一步必须等某个人签字或确认才能往下走？",
    "retry": "有没有做完发现不行、要回头重做的情况？回到哪一步重做？",
    "experience": "哪一步最靠经验判断，新人最容易做错？",
}

_VALIDATOR_QUESTIONS = {
    "missing_end": "整件事做到哪一步就算结束了？",
    "missing_start": "这件事是从什么情况开始的？",
    "cycle_detected": "流程里有一处绕回了前面的步骤，这是要回头重做吗？回到哪一步？",
    "isolated_node": "「{label}」这一步是在哪一步之后做的？",
    "decision_needs_two_branches": "「{label}」这里判断之后，另一种情况是怎么处理的？",
    "parallel_split_needs_two": "「{label}」之后同时进行的是哪几件事？",
    "parallel_join_needs_two": "「{label}」之前，是哪几件同时进行的事汇到一起？",
    "merge_needs_two": "「{label}」之前是哪几条路汇到一起？",
}

# Ontology follow-ups (docs/expert-workflow-collection/ontology/MANUFACTURING_OPERATIONAL_ONTOLOGY.md
# section 9): asked once the structure is valid (after unverified steps, validator errors and
# missing branch conditions) but before the model's own uncertainties -- in a trial run with a
# real model, almost every answer produced a new uncertainty (priority 40), so anything ranked
# below "model" was never reached within max_questions. The expert's answer is turned into node fields by review_agent (via
# ontology_capture), never by the model.
CRITERION_QUESTION = "「{label}」这里判断走哪条路时，有具体的标准吗？比如正常应该是多少、到多少就不行？没有具体数值、靠经验看也可以直接说。"
TIMING_QUESTION = "「{label}」要等人确认，一般最晚多久要有结果？超时了会找谁？没有明确的时间要求也可以直接说。"
ONTOLOGY_KINDS = ("criterion", "timing")
MAX_ONTOLOGY_GAPS_PER_KIND = 2  # keep the interview short: only the first few decision / approval steps

# Severity tiers (lower = asked first). The interview always asks the single most severe open
# item -- questions that decide whether the graph is usable at all come before structure,
# structure before detail, and the model's own follow-up doubts come last. New items (rule
# gaps that appear after an edit, or model doubts) are slotted into the same ordering by tier
# rather than jumping the queue, so one answer can't pull the interview into a long tangent
# around a single step while the process as a whole is still incomplete.
#   Tier 1 (10-19) fatal:     a step nobody said / structural errors (no start or end, isolated
#                             step, a decision with one way out, a split that never joins)
#   Tier 2 (20-29) structure: decision conditions, then whether exceptions / approvals /
#                             rework / simultaneous work exist at all
#   Tier 3 (30-39) detail:    who does each step, decision thresholds, approval time limits,
#                             where experience matters
#   Tier 4 (40+)   model:     doubts the model raised itself
PRIORITY = {"unverified_node": 10, "validator": 15, "decision_condition": 20, "coverage": 22,
            "missing_actor": 30, "criterion": 32, "timing": 33, "model": 40}

# Coverage questions differ in how much a "no answer" leaves the graph incomplete: a missing
# exception path or sign-off changes the shape of the process, "where does experience matter"
# is valuable detail but never makes the graph wrong.
COVERAGE_PRIORITY = {"exceptions": 22, "approval": 23, "retry": 24, "parallel": 25, "experience": 38}

TIER_LABELS = ((20, "fatal"), (30, "structure"), (40, "detail"))


def tier(gap: dict) -> str:
    """"fatal" / "structure" / "detail" / "model" -- for display and logging."""
    for upper, name in TIER_LABELS:
        if gap["priority"] < upper:
            return name
    return "model"


def _gap(kind: str, text: str, node_ids: Iterable[str] = (), *, source: str = "rule", key: str = "",
         priority: int | None = None) -> dict:
    node_ids = list(node_ids)
    return {
        "id": f"{kind}:{key or ','.join(node_ids)}",
        "kind": kind,
        "priority": priority if priority is not None else PRIORITY.get(kind.split("/")[0], 50),
        "text": text,
        "node_ids": node_ids,
        "status": "open",
        "source": source,
    }


def rule_gaps(graph: dict, *, mode: str) -> list[dict]:
    """mode: "create"/"edit" (the narrator's own process -- ask everything) or
    "annotate"/"arbitrate" (reviewing someone else's graph -- only structural problems;
    imported records carry no evidence quotes, and coverage questions are the author's job)."""
    nodes = graph.get("nodes", [])
    by_id = {n["node_id"]: n for n in nodes}
    authoring = mode in ("create", "edit")
    out: list[dict] = []

    if authoring:
        for n in nodes:
            if n["node_type"] in ("start", "end"):
                continue
            if not n.get("evidence"):
                out.append(_gap("unverified_node",
                                f"您的讲述里我没找到「{n['label']}」这一步的原话，这一步是您说的吗，还是我理解错了？",
                                [n["node_id"]]))

    for issue in graph_validator.validate(graph):
        if issue["level"] != "error":
            continue
        template = _VALIDATOR_QUESTIONS.get(issue["code"])
        if not template:
            continue
        label = by_id.get(issue.get("node_id") or "", {}).get("label", "")
        out.append(_gap("validator", template.format(label=label),
                        [issue["node_id"]] if issue.get("node_id") else [], key=issue["code"] + ":" + (issue.get("node_id") or "")))

    for n in nodes:
        if n["node_type"] != "decision":
            continue
        missing = [e for e in graph.get("edges", []) if e["from"] == n["node_id"] and e["edge_type"] == "conditional"
                   and not (e.get("condition") or "").strip()]
        if missing:
            out.append(_gap("decision_condition", f"「{n['label']}」这里，各种情况分别是什么条件？分别接着做什么？", [n["node_id"]]))

    if authoring:
        types = {n["node_type"] for n in nodes}
        has_retry = any((n.get("retry_semantics") or {}).get("enabled") for n in nodes)
        present = {
            "exceptions": "decision" in types,
            "parallel": "parallel_split" in types,
            "approval": "approval" in types,
            "retry": has_retry,
            "experience": False,
        }
        for key, text in COVERAGE_QUESTIONS.items():
            if not present[key]:
                out.append(_gap("coverage", text, key=key, priority=COVERAGE_PRIORITY[key]))

        # Ontology follow-ups, one per step, for steps the expert hasn't covered yet. Once the
        # gap was asked, its "asked"/"resolved" status carries over by id even when the expert
        # declined (field still empty), so it is never asked twice.
        # The cap counts steps, not open questions, so answering one never pulls in a third.
        decisions = [n for n in nodes if n["node_type"] == "decision"][:MAX_ONTOLOGY_GAPS_PER_KIND]
        for n in decisions:
            if not n.get("evaluation_criteria"):
                out.append(_gap("criterion", CRITERION_QUESTION.format(label=n["label"]), [n["node_id"]]))
        approvals = [n for n in nodes if n["node_type"] == "approval"][:MAX_ONTOLOGY_GAPS_PER_KIND]
        for n in approvals:
            if not n.get("sla_config"):
                out.append(_gap("timing", TIMING_QUESTION.format(label=n["label"]), [n["node_id"]]))

        no_actor = [n for n in nodes if n["node_type"] in ("activity", "approval", "handoff") and not n.get("actor_roles")]
        if no_actor:
            names = "".join(f"「{n['label']}」" for n in no_actor[:6])
            out.append(_gap("missing_actor", f"这几个步骤分别是谁做的：{names}？", [n["node_id"] for n in no_actor], key="all"))
    return out


def model_gap(text: str, node_ids: list[str]) -> dict:
    # Deterministic id (not Python's per-process randomized hash) -- ids are persisted.
    return _gap("model", text, node_ids, source="model", key=hashlib.md5(text.encode("utf-8")).hexdigest()[:10])


def unverified_model_node_gap(text: str, node_id: str) -> dict:
    """A step the model added during review whose evidence quote isn't in what the expert said.
    Same severity as an unverified step from the first draft (tier 1): a step nobody said must
    be settled before anything about its details is asked."""
    return _gap("unverified_node", text, [node_id], source="model",
                key="review:" + hashlib.md5(text.encode("utf-8")).hexdigest()[:10])


# At most this many doubts the model raised itself, per session (the first draft's included).
# They are the bottom tier anyway; the cap keeps a talkative model from turning every answer
# into a new thread to pull on.
MAX_MODEL_GAPS = 4


def admit_model_gaps(gaps: list[dict], candidates: Iterable[dict], *, answered: dict | None) -> list[dict]:
    """Which of the model's new doubts get onto the list. Anti-divergence rules:
    - a doubt about a step that the expert has just been asked about is dropped -- the expert
      just answered on that step; drilling straight back into it is the tangent we avoid;
    - a doubt raised while answering one of the model's *own* doubts is dropped (follow-ups
      are one level deep: a follow-up never spawns another follow-up);
    - the session total stays within MAX_MODEL_GAPS."""
    if answered is not None and answered.get("source") == "model":
        return []
    answered_nodes = set((answered or {}).get("node_ids") or [])
    room = MAX_MODEL_GAPS - sum(1 for g in gaps if g["kind"] == "model")
    out: list[dict] = []
    for g in candidates:
        if room <= 0:
            break
        if answered_nodes & set(g.get("node_ids") or []):
            continue
        out.append(g)
        room -= 1
    return out


def refresh(existing: list[dict], graph: dict, *, mode: str, new_model_gaps: Iterable[dict] = ()) -> list[dict]:
    """Recompute rule gaps against the current graph and merge with the existing list:
    statuses carry over by id; a rule gap that no longer applies becomes resolved; model gaps
    stay as they were; new model gaps are appended (deduped by id)."""
    old = {g["id"]: g for g in existing}
    current_rule = {g["id"]: g for g in rule_gaps(graph, mode=mode)}
    out: list[dict] = []
    for gid, g in old.items():
        if g["source"] == "rule":
            if gid in current_rule:
                out.append({**current_rule[gid], "status": g["status"]})
            elif g["status"] in ("open", "asked"):
                out.append({**g, "status": "resolved"})
            else:
                out.append(g)
        else:
            out.append(g)
    for gid, g in current_rule.items():
        if gid not in old:
            out.append(g)
    known = {g["id"] for g in out}
    for g in new_model_gaps:
        if g["id"] not in known:
            out.append(g)
            known.add(g["id"])
    return out


def open_gaps(gaps: list[dict]) -> list[dict]:
    return sorted((g for g in gaps if g["status"] == "open"), key=lambda g: (g["priority"], g["id"]))


def mark(gaps: list[dict], ids: Iterable[str], status: str) -> list[dict]:
    ids = set(ids)
    return [{**g, "status": status} if g["id"] in ids and g["status"] in ("open", "asked") else g for g in gaps]
