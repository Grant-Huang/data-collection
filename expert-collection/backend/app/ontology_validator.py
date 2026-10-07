"""Ontology Validator -- rule table in docs/expert-workflow-collection/ontology/
MANUFACTURING_OPERATIONAL_ONTOLOGY.md section 7. Pure rule-based like graph_validator (no LLM),
and same issue shape ({level, code, message, node_id?, edge_id?}).

Rough split: `error` = the ontology contradicts itself or points at nothing; `warning` = a gap
the expert should still fill in (missing role on an escalation, a decision with no measurable
criterion, low confidence with nothing backing it). Not wired into the confirm gate -- see the
design doc for why.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from .ontology import REGISTRY_ID_FIELDS, OntologyView

# ISO 8601 duration (PnYnMnWnDTnHnMnS); at least one component, "T" must be followed by a time part.
_DURATION_RE = re.compile(
    r"^P(?!$)(\d+Y)?(\d+M)?(\d+W)?(\d+D)?(T(?=\d)(\d+H)?(\d+M)?(\d+(\.\d+)?S)?)?$"
)
LOW_CONFIDENCE = 0.6


def _issue(level: str, code: str, message: str, node_id: Optional[str] = None,
           edge_id: Optional[str] = None) -> dict[str, str]:
    d = {"level": level, "code": code, "message": message}
    if node_id:
        d["node_id"] = node_id
    if edge_id:
        d["edge_id"] = edge_id
    return d


def _in_band(value: float, band) -> bool:
    if band.lower is not None and (value < band.lower or (value == band.lower and not band.lower_inclusive)):
        return False
    if band.upper is not None and (value > band.upper or (value == band.upper and not band.upper_inclusive)):
        return False
    return True


def validate(view: OntologyView, graph: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    ont = view.ontology
    nodes = {n["node_id"]: n for n in graph.get("nodes", [])}
    edges = graph.get("edges", [])

    # --- registry integrity -------------------------------------------------------------
    ids: dict[str, set[str]] = {}
    for reg, idf in REGISTRY_ID_FIELDS.items():
        seen: set[str] = set()
        for obj in getattr(ont, reg):
            oid = getattr(obj, idf)
            if oid in seen:
                issues.append(_issue("error", "ont_duplicate_id", f"{reg} 中 id 重复：{oid}"))
            seen.add(oid)
        ids[reg] = seen

    def ref(reg: str, oid: Optional[str], where: str, node_id: Optional[str] = None,
            edge_id: Optional[str] = None) -> None:
        if oid and oid not in ids[reg]:
            issues.append(_issue("error", "ont_dangling_ref", f"{where} 引用的 {oid} 在 {reg} 中不存在",
                                 node_id=node_id, edge_id=edge_id))

    def duration(value: Optional[str], where: str, node_id: Optional[str] = None) -> None:
        if value and not _DURATION_RE.match(value):
            issues.append(_issue("error", "ont_bad_duration",
                                 f"{where} 的时长 {value!r} 不是 ISO 8601 格式（如 PT4H、P3D）", node_id=node_id))

    def assertion(a, where: str, node_id: Optional[str] = None, *, check_inferred: bool = True) -> None:
        if a is None:
            return
        for ev in a.evidence_ids:
            ref("evidence", ev, where, node_id)
        ref("scopes", a.scope_id, where, node_id)
        if a.confidence is not None and a.confidence < LOW_CONFIDENCE and not a.evidence_ids:
            issues.append(_issue("warning", "ont_low_confidence_no_evidence",
                                 f"{where} 置信度 {a.confidence} 偏低且没有任何证据", node_id=node_id))
        if check_inferred and a.confidence_basis == "llm_inferred" and not a.expert_confirmed:
            issues.append(_issue("warning", "ont_inferred_unconfirmed",
                                 f"{where} 由模型推断，尚未经专家确认", node_id=node_id))

    # --- roles ----------------------------------------------------------------------------
    for r in ont.roles:
        ref("roles", r.reports_to, f"角色 {r.name}")
        assertion(r.assertion, f"角色 {r.name}")

    # --- checks: threshold + expected value ----------------------------------------------
    for c in ont.checks:
        where = f"判据「{c.name}」"
        has_numbers = any(b.lower is not None or b.upper is not None for b in c.limits) or (
            c.expected is not None and c.expected.target is not None)
        if c.kind == "numeric" and has_numbers and not c.unit:
            issues.append(_issue("warning", "ont_check_missing_unit", f"{where} 有数值但没有单位"))
        for b in c.limits:
            if b.lower is not None and b.upper is not None and b.lower > b.upper:
                issues.append(_issue("error", "ont_limit_inverted",
                                     f"{where} 的 {b.band} 区间下限 {b.lower} 大于上限 {b.upper}"))
        normal = [b for b in c.limits if b.band == "normal"]
        if c.expected is not None and c.expected.target is not None and normal and not any(
                _in_band(c.expected.target, b) for b in normal):
            issues.append(_issue("warning", "ont_expected_outside_normal",
                                 f"{where} 的预期值 {c.expected.target} 不在 normal 区间内"))
        has_expected = c.expected is not None and (c.expected.target is not None or c.expected.value)
        if not has_expected and not c.limits and not c.allowed_values and not c.aggregation:
            issues.append(_issue("warning", "ont_check_empty", f"{where} 既没有预期值也没有阈值"))
        ref("exception_cases", c.on_violation_exception_id, where)
        assertion(c.assertion, where)

    # --- time constraints -----------------------------------------------------------------
    for t in ont.time_constraints:
        where = f"时间约束 {t.time_constraint_id}"
        duration(t.duration, where)
        if not t.duration:
            issues.append(_issue("warning", "ont_time_missing_duration", f"{where} 没有给出时长"))
        if t.on_violation:
            ref("escalation_policies", t.on_violation.escalation_policy_id, where)
        assertion(t.assertion, where)

    # --- permissions ----------------------------------------------------------------------
    for p in ont.permissions:
        where = f"权限 {p.permission_id}"
        if not p.allowed_role_ids:
            issues.append(_issue("error", "ont_permission_no_roles", f"{where}（{p.action}）没有任何可执行角色"))
        for rid in p.allowed_role_ids:
            ref("roles", rid, where)
        ref("escalation_policies", p.escalation_policy_id, where)
        assertion(p.assertion, where)

    # --- exceptions -----------------------------------------------------------------------
    for x in ont.exception_cases:
        where = f"异常 {x.name or x.exception_id}"
        ref("checks", x.trigger.check_id, where)
        ref("time_constraints", x.trigger.time_constraint_id, where)
        ref("escalation_policies", x.escalation_policy_id, where)
        if x.handler_node_id and x.handler_node_id not in nodes:
            issues.append(_issue("error", "ont_dangling_ref", f"{where} 的处置节点 {x.handler_node_id} 不存在"))
        if not x.handler_node_id and not x.escalation_policy_id:
            issues.append(_issue("warning", "ont_exception_unhandled", f"{where} 既没有处置节点也没有升级策略"))
        temp = x.temporary_measure
        if temp is not None:
            ref("permissions", temp.get("permission_id"), where)
            expiration = temp.get("expiration") or {}
            if not (expiration.get("duration") or expiration.get("lot_count") or temp.get("revocation_trigger")):
                issues.append(_issue("error", "ont_temp_measure_no_expiry",
                                     f"{where} 的临时措施没有有效期也没有失效条件"))
            duration(expiration.get("duration"), where)
        assertion(x.assertion, where)

    # --- escalation policies --------------------------------------------------------------
    for e in ont.escalation_policies:
        where = f"升级策略 {e.name or e.policy_id}"
        if not e.levels:
            issues.append(_issue("error", "ont_escalation_no_levels", f"{where} 没有任何升级层级"))
        levels = [lv.level for lv in e.levels]
        if any(b <= a for a, b in zip(levels, levels[1:])):
            issues.append(_issue("error", "ont_escalation_level_order", f"{where} 的层级号不是严格递增：{levels}"))
        for lv in e.levels:
            if lv.to_role_id:
                ref("roles", lv.to_role_id, where)
            else:
                issues.append(_issue("warning", "ont_escalation_missing_role",
                                     f"{where} 第 {lv.level} 级没有指定升级给哪个角色"))
            duration(lv.after, where)
        if e.trigger:
            duration(e.trigger.within_duration, where)
        assertion(e.assertion, where)

    # --- node links -----------------------------------------------------------------------
    preds: dict[str, list[str]] = {}
    for e in edges:
        preds.setdefault(e["to"], []).append(e["from"])
    perms = {p.permission_id: p for p in ont.permissions}
    for nid, links in view.node_links.items():
        node = nodes.get(nid, {})
        label = f"步骤「{node.get('label', nid)}」"
        for rid in (links.raci.responsible + links.raci.accountable
                    + links.raci.consulted + links.raci.informed):
            ref("roles", rid, label, nid)
        for cid in links.check_ids:
            ref("checks", cid, label, nid)
        for tid in links.time_constraint_ids:
            ref("time_constraints", tid, label, nid)
        for pid in links.permission_ids:
            ref("permissions", pid, label, nid)
        for xid in links.exception_ids:
            ref("exception_cases", xid, label, nid)
        # Nodes are LLM-extracted by design and confirmed at the end of collection, so
        # "inferred, not yet confirmed" is the normal state for a node -- not worth a warning.
        assertion(links.assertion, label, nid, check_inferred=False)

        if node.get("node_type") == "approval" and not links.permission_ids:
            issues.append(_issue("warning", "ont_approval_without_permission",
                                 f"{label} 是审批节点，但没有声明谁有权审批", nid))
        if node.get("node_type") == "decision" and not links.check_ids and any(
                e["from"] == nid and e.get("edge_type") == "conditional" for e in edges):
            issues.append(_issue("warning", "ont_decision_without_check",
                                 f"{label} 有条件分支，但没有可量化的判据", nid))

        # Separation of duties: approver must not be the one who did the work being approved,
        # i.e. a responsible role of a direct predecessor `activity` node.
        performers: set[str] = set()
        for pred in preds.get(nid, []):
            if nodes.get(pred, {}).get("node_type") == "activity" and pred in view.node_links:
                performers.update(view.node_links[pred].raci.responsible)
        for pid in links.permission_ids:
            p = perms.get(pid)
            if p and p.separation_of_duties:
                overlap = performers.intersection(p.allowed_role_ids)
                if overlap:
                    issues.append(_issue("error", "ont_sod_violation",
                                         f"{label} 要求职责分离，但审批角色 {sorted(overlap)} 同时执行了被审批的前序工作",
                                         nid))

    for eid, el in view.edge_links.items():
        ref("time_constraints", el.time_constraint_id, f"边 {eid}", edge_id=eid)
        ref("exception_cases", el.exception_id, f"边 {eid}", edge_id=eid)

    return issues
