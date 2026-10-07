"""Accumulated vocabulary and ontology entries -- append-only, never written back.

Grant (2026-10-07): build up a vocabulary from expert entry and annotation, but don't change
the entry flow or rewrite existing records with it yet ("只累计，不回归"); tidying records against
it comes later. Ontology entries are accumulated the same way. The schema itself
(docs/expert-workflow-collection/schema/workflow_graph_schema_v3.json) is not touched here.

Two layers in one store (db.accumulated_entries):
- "term": the words people actually used -- role names, step names, decision questions,
  check names, units, branch conditions. Kept verbatim; no synonym merging (that is the later
  tidy-up step, done by a person looking at this list).
- "ontology": the structured objects ontology.lift_v2_record derives from a graph (roles,
  checks, time constraints, permissions, exception cases, escalation policies). Two objects
  with the same content (ignoring per-workflow ids and provenance) are one entry.

Each entry records where it was seen (sources, deduplicated by source) and when it was first
and last seen. Accumulating the same source twice changes nothing but last_seen_at, so
re-confirming a workflow or re-running the backfill is safe. Nothing is ever removed: if a
workflow is reopened and a role renamed, the old name stays in the vocabulary.

Sources (see accumulate_from_*):
- an expert workflow, when the expert confirms it;
- an annotation that accepted a record (its current graph) or revised it (the revised graph).
  Rejected records contribute nothing.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from . import dataset_records, db, ontology

logger = logging.getLogger(__name__)

TERM_KINDS = {
    "role": "角色",
    "step": "步骤",
    "decision": "判断",
    "condition": "分支条件",
    "check": "检查项",
    "unit": "单位",
}
ONTOLOGY_KINDS = {
    "roles": "角色",
    "checks": "检查/判断标准",
    "time_constraints": "时限",
    "permissions": "权限",
    "exception_cases": "异常情况",
    "escalation_policies": "升级规则",
}
MAX_SOURCES_PER_ENTRY = 50  # enough to trace an entry; the count keeps growing past it

_STEP_TYPES = {"activity", "approval", "handoff", "wait"}
# Per-workflow ids and provenance: dropped before comparing ontology objects across workflows.
# Role ids are name-based ("role_质检") and so are kept -- they mean the same thing everywhere.
_LOCAL_KEYS = {"check_id", "time_constraint_id", "permission_id", "exception_id", "policy_id",
               "escalation_policy_id", "on_violation_exception_id", "source_criterion_id",
               "handler_node_id", "anchor_ref", "assertion", "evidence_ids", "entity_ids"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(text: Any) -> str:
    return " ".join(str(text).split()) if isinstance(text, str) else ""


# --- extraction (pure) ---------------------------------------------------------------------

def terms_from_graph(graph: dict) -> list[tuple[str, str, str]]:
    """(kind, term, step label it appeared on) for every term in a graph, verbatim."""
    by_id = {n["node_id"]: n for n in graph.get("nodes", [])}
    out: list[tuple[str, str, str]] = []
    for n in graph.get("nodes", []):
        label = _clean(n.get("label"))
        if n.get("node_type") in _STEP_TYPES and label:
            out.append(("step", label, label))
        if n.get("node_type") == "decision":
            for q in (n.get("decision_question"), n.get("label")):
                if _clean(q):
                    out.append(("decision", _clean(q), label))
                    break
        for r in n.get("actor_roles") or []:
            out.append(("role", _clean(r), label))
        for row in n.get("approval_matrix") or []:
            for r in (row or {}).get("required_roles") or []:
                out.append(("role", _clean(r), label))
        sla = n.get("sla_config") or {}
        if _clean(sla.get("escalate_to_role")):
            out.append(("role", _clean(sla["escalate_to_role"]), label))
        for c in n.get("evaluation_criteria") or []:
            if _clean(c.get("name")):
                out.append(("check", _clean(c["name"]), label))
            if _clean(c.get("unit")):
                out.append(("unit", _clean(c["unit"]), label))
    for e in graph.get("edges", []):
        if e.get("edge_type") == "conditional" and _clean(e.get("condition")):
            out.append(("condition", _clean(e["condition"]), _clean(by_id.get(e["from"], {}).get("label"))))
    return [t for t in out if t[1]]


def _strip_local(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_local(v) for k, v in value.items() if k not in _LOCAL_KEYS}
    if isinstance(value, list):
        return [_strip_local(v) for v in value]
    return value


def _ontology_label(kind: str, obj: dict) -> str:
    if kind == "roles":
        return obj.get("name") or obj.get("role_id", "")
    if kind == "time_constraints":
        return obj.get("description") or f"{obj.get('kind', '')} {obj.get('duration') or ''}".strip()
    if kind == "permissions":
        roles = "、".join(r.removeprefix("role_") for r in obj.get("allowed_role_ids") or [])
        return f"{obj.get('action', '')}：{roles}" if roles else obj.get("action", "")
    if kind == "exception_cases":
        return obj.get("name") or (obj.get("trigger") or {}).get("description") or "异常情况"
    return obj.get("name") or obj.get("description") or kind


def ontology_entries_from_graph(graph: dict) -> list[tuple[str, str, dict, list[str]]]:
    """(kind, content key, content without per-workflow ids, step labels linked to it)."""
    view = ontology.lift_v2_record({"graph": graph}).model_dump(exclude_none=True)
    labels = {n["node_id"]: _clean(n.get("label")) for n in graph.get("nodes", [])}
    linked: dict[str, list[str]] = {}
    for nid, links in view.get("node_links", {}).items():
        for field in ("check_ids", "time_constraint_ids", "permission_ids", "exception_ids"):
            for oid in links.get(field) or []:
                linked.setdefault(oid, []).append(labels.get(nid, nid))
        raci = links.get("raci") or {}
        for rids in raci.values():
            for rid in rids if isinstance(rids, list) else [rids]:
                if isinstance(rid, str):
                    linked.setdefault(rid, []).append(labels.get(nid, nid))
    out = []
    reg = view.get("ontology", {})
    for kind in ONTOLOGY_KINDS:
        id_field = ontology.REGISTRY_ID_FIELDS[kind]
        for obj in reg.get(kind, []):
            content = _strip_local(obj)
            key = hashlib.sha1(json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
            out.append((kind, key, content, sorted(set(linked.get(obj.get(id_field), [])))))
    return out


# --- accumulation (append-only) ------------------------------------------------------------

def _add(layer: str, kind: str, key: str, label: str, source: dict, *, step: str = "", content: dict | None = None) -> None:
    now = _now()
    entry = db.get_accumulated(layer, kind, key) or {
        "layer": layer, "kind": kind, "key": key, "label": label, "content": content,
        "sources": [], "source_count": 0, "steps": [], "first_seen_at": now,
    }
    entry["last_seen_at"] = now
    sid = (source["type"], source["id"])
    if not any((s["type"], s["id"]) == sid for s in entry["sources"]):
        entry["source_count"] += 1
        if len(entry["sources"]) < MAX_SOURCES_PER_ENTRY:
            entry["sources"].append({**source, "seen_at": now})
    if step and step not in entry["steps"] and len(entry["steps"]) < MAX_SOURCES_PER_ENTRY:
        entry["steps"].append(step)
    db.upsert_accumulated(entry)


def accumulate_graph(graph: dict, source: dict) -> None:
    """Add every term and ontology entry in `graph`, attributed to `source`
    ({"type": "expert_workflow"|"annotation", "id": ..., "name": ...})."""
    for kind, term, step in terms_from_graph(graph):
        _add("term", kind, term, term, source, step=step)
    for kind, key, content, steps in ontology_entries_from_graph(graph):
        label = _ontology_label(kind, content)
        for step in steps or [""]:
            _add("ontology", kind, key, label, source, step=step, content=content)


def _safe(fn, *args) -> None:
    # Accumulating is a side effect of saving: it must never make the save itself fail.
    try:
        fn(*args)
    except Exception:  # noqa: BLE001
        logger.exception("vocabulary accumulation failed")


def accumulate_from_workflow(record: dict) -> None:
    """Called when an expert confirms a workflow."""
    _safe(accumulate_graph, record.get("graph") or {},
          {"type": "expert_workflow", "id": record["id"], "name": record.get("name") or record["id"]})


def accumulate_from_annotation(entry: dict, current_graph: dict | None, record_name: str = "") -> None:
    """Called when an annotation is saved. Counts the graph the annotator stood behind: the
    revised graph when they corrected it, the record's current graph when they accepted it.
    Rejections, and "needs revision" without a corrected graph, contribute nothing."""
    graph = entry.get("revised_graph") or (current_graph if entry.get("verdict") == "accepted" else None)
    if not graph:
        return
    _safe(accumulate_graph, graph, {"type": "annotation", "id": entry["annotation_id"],
                                    "name": record_name or entry.get("record_id", ""),
                                    "version_id": entry.get("version_id"), "record_id": entry.get("record_id")})


def backfill() -> dict:
    """Accumulate from everything already stored: confirmed workflows, and annotations that
    accepted or revised a record. Idempotent (same sources -> same counts)."""
    workflows = [r for r in db.list_all() if r.get("status") == "expert_confirmed"]
    for r in workflows:
        accumulate_from_workflow(r)
    annotations = 0
    exported: dict[str, list[dict]] = {}
    for a in db.list_all_annotations():
        if a.get("verdict") == "rejected":
            continue
        graph = None
        if not a.get("revised_graph") and a.get("verdict") == "accepted":
            # The graph the annotator accepted: the record's latest revision, else the record
            # as exported (expert_collected versions read the live workflow).
            vid, rid = a["version_id"], a.get("record_id")
            revisions = db.list_revisions(vid, rid)
            if revisions:
                graph = revisions[-1].get("graph")
            else:
                if vid not in exported:
                    version = db.get_dataset_version(vid)
                    exported[vid] = dataset_records.records_for_export(version) if version else []
                graph = next((r.get("graph") for r in exported[vid] if r.get("record_id") == rid), None)
        if a.get("revised_graph") or graph:
            accumulate_from_annotation(a, graph)
            annotations += 1
    return {"workflows": len(workflows), "annotations": annotations}


# --- read ----------------------------------------------------------------------------------

def list_entries(layer: str, kind: str | None = None) -> list[dict]:
    """Most-used first, then most recently seen."""
    rows = sorted(db.list_accumulated(layer, kind), key=lambda e: e["last_seen_at"], reverse=True)
    return sorted(rows, key=lambda e: -e["source_count"])  # stable: ties keep most-recent-first


def summary() -> dict:
    out: dict[str, Any] = {"term": {}, "ontology": {}}
    for layer, kinds in (("term", TERM_KINDS), ("ontology", ONTOLOGY_KINDS)):
        rows = db.list_accumulated(layer)
        for k, label in kinds.items():
            out[layer][k] = {"label": label, "count": sum(1 for e in rows if e["kind"] == k)}
    return out


def kinds() -> dict[str, dict[str, str]]:
    return {"term": TERM_KINDS, "ontology": ONTOLOGY_KINDS}

