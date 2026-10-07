"""Manufacturing Operational Ontology (MOO) v1 -- docs/expert-workflow-collection/ontology/
MANUFACTURING_OPERATIONAL_ONTOLOGY.md, schema/workflow_graph_schema_v3.json.

Two things live here:
1. Pydantic models for the ontology registry (`Ontology`) and the per-node / per-edge id links
   (`NodeLinks`, `EdgeLinks`), mirroring the v3 schema's $defs.
2. `lift_v2_record()`: a deterministic (no LLM) projection of an existing v2 / Phase 3-A record
   into that ontology view. It never mutates the stored record -- the graph stays the source of
   truth, the ontology is a derived, re-computable view (section 6 of the design doc). If the
   record already carries an explicit v3 `ontology` block, those objects win and lifted objects
   are only added for ids that aren't already registered.
"""
from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

ConfidenceBasis = Literal[
    "expert_stated", "expert_confirmed", "multi_expert_agreement",
    "document_backed", "data_verified", "llm_inferred",
]


class Assertion(BaseModel):
    """Shared shape every ontology object can carry (Palantir-style interface): how much we
    trust this piece of structured knowledge, why, and where it holds."""
    confidence: Optional[float] = None
    confidence_basis: Optional[ConfidenceBasis] = None
    evidence_ids: list[str] = Field(default_factory=list)
    scope_id: Optional[str] = None
    expert_confirmed: bool = False
    source_turn_ids: list[str] = Field(default_factory=list)
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None


class Role(BaseModel):
    role_id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    level: Optional[int] = None
    # Default escalation chain source.
    reports_to: Optional[str] = None
    qualifications: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    assertion: Optional[Assertion] = None


class LimitBand(BaseModel):
    band: Literal["normal", "warning", "critical", "reject"]
    lower: Optional[float] = None
    upper: Optional[float] = None
    lower_inclusive: bool = True
    upper_inclusive: bool = True


class ExpectedValue(BaseModel):
    target: Optional[float] = None
    tolerance_minus: Optional[float] = None
    tolerance_plus: Optional[float] = None
    value: Optional[str] = None
    description: Optional[str] = None


class Check(BaseModel):
    """Threshold (`limits`: where it stops being OK) + expected value (`expected`: what it
    should normally be) -- deliberately two fields, see design doc section 5."""
    check_id: str
    name: str
    metric: Optional[str] = None
    kind: Literal["numeric", "categorical", "boolean", "text"]
    unit: Optional[str] = None
    expected: Optional[ExpectedValue] = None
    limits: list[LimitBand] = Field(default_factory=list)
    # v2 `thresholds` original text, kept verbatim so nothing is lost when parsing fails.
    limits_text: Optional[dict[str, Any]] = None
    allowed_values: list[str] = Field(default_factory=list)
    aggregation: Optional[dict[str, Any]] = None
    measurement: Optional[dict[str, Any]] = None
    on_violation_exception_id: Optional[str] = None
    source_criterion_id: Optional[str] = None
    assertion: Optional[Assertion] = None


class ViolationHandling(BaseModel):
    action: Literal["escalate", "notify", "auto_reassign", "none"] = "none"
    escalation_policy_id: Optional[str] = None


class TimeConstraint(BaseModel):
    time_constraint_id: str
    kind: Literal[
        "expected_duration", "deadline", "target", "warn_threshold",
        "validity_window", "waiting_period", "frequency",
    ]
    duration: Optional[str] = None  # ISO 8601, e.g. PT4H
    anchor: Optional[Literal[
        "previous_node_completed", "node_started", "workflow_start", "event_occurred", "manual_start",
    ]] = None
    anchor_ref: Optional[str] = None
    enforced: Optional[bool] = None
    on_violation: Optional[ViolationHandling] = None
    description: Optional[str] = None
    assertion: Optional[Assertion] = None


class EvidenceRequirement(BaseModel):
    """Operational evidence a step must leave behind (vs. `Evidence`, which is why we believe
    a piece of knowledge)."""
    artifact_type: Optional[str] = None
    description: str
    mandatory: bool = True


class SubmissionCriterion(BaseModel):
    kind: Optional[Literal["actor", "parameter", "object_state"]] = None
    description: str
    expression: Optional[str] = None


class Permission(BaseModel):
    """A controlled action on a step -- the Palantir Action Type analogue."""
    permission_id: str
    action: Literal[
        "execute", "approve", "reject", "release", "bypass", "waive",
        "stop_line", "modify_parameter", "sign_off",
    ]
    allowed_role_ids: list[str] = Field(default_factory=list)
    sequence: Optional[Literal["sequential", "parallel", "any_one"]] = None
    submission_criteria: list[SubmissionCriterion] = Field(default_factory=list)
    separation_of_duties: bool = False
    delegable: Optional[bool] = None
    required_evidence: list[EvidenceRequirement] = Field(default_factory=list)
    failure_message: Optional[str] = None
    escalation_policy_id: Optional[str] = None
    assertion: Optional[Assertion] = None


class Evidence(BaseModel):
    evidence_id: str
    kind: Literal["expert_quote", "document", "system_record", "measurement", "observation", "standard"]
    content: Optional[str] = None
    source_ref: Optional[str] = None
    turn_id: Optional[str] = None
    captured_by_role_id: Optional[str] = None
    captured_at: Optional[str] = None


class Scope(BaseModel):
    """Where a piece of knowledge applies -- NOT the same as an exception's containment
    (where a problem's impact reaches)."""
    scope_id: str
    name: Optional[str] = None
    selectors: dict[str, list[str]] = Field(default_factory=dict)
    conditions: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)


class ExceptionTrigger(BaseModel):
    kind: Literal["check_violation", "timeout", "event", "rejection", "repeat_occurrence"]
    check_id: Optional[str] = None
    time_constraint_id: Optional[str] = None
    description: Optional[str] = None


class ExceptionCase(BaseModel):
    exception_id: str
    name: Optional[str] = None
    trigger: ExceptionTrigger
    severity: Optional[Literal["minor", "major", "critical"]] = None
    handler_node_id: Optional[str] = None
    # Same shape as Phase 3-A `containment_scope`; kept as a dict to stay in lock-step with it.
    containment: Optional[dict[str, Any]] = None
    # {description, expiration, revocation_trigger, permission_id} -- Phase 3-A shapes reused.
    temporary_measure: Optional[dict[str, Any]] = None
    escalation_policy_id: Optional[str] = None
    resolution_criteria: Optional[str] = None
    assertion: Optional[Assertion] = None


class EscalationTrigger(BaseModel):
    kind: Optional[Literal["timeout", "severity", "repeat", "rejection", "manual"]] = None
    repeat_count: Optional[int] = None
    within_duration: Optional[str] = None
    description: Optional[str] = None


class EscalationLevel(BaseModel):
    level: int
    # Optional in the model (lifted v2 data often doesn't say who), required by the v3 schema;
    # the validator reports the gap as `ont_escalation_missing_role`.
    to_role_id: Optional[str] = None
    after: Optional[str] = None
    action: Optional[Literal["notify", "reassign", "approval_required", "stop_production", "create_capa"]] = None


class EscalationPolicy(BaseModel):
    policy_id: str
    name: Optional[str] = None
    trigger: Optional[EscalationTrigger] = None
    levels: list[EscalationLevel] = Field(default_factory=list)
    terminal_action: Optional[str] = None
    assertion: Optional[Assertion] = None


class Ontology(BaseModel):
    roles: list[Role] = Field(default_factory=list)
    checks: list[Check] = Field(default_factory=list)
    time_constraints: list[TimeConstraint] = Field(default_factory=list)
    permissions: list[Permission] = Field(default_factory=list)
    exception_cases: list[ExceptionCase] = Field(default_factory=list)
    escalation_policies: list[EscalationPolicy] = Field(default_factory=list)
    scopes: list[Scope] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class Raci(BaseModel):
    responsible: list[str] = Field(default_factory=list)
    accountable: list[str] = Field(default_factory=list)
    consulted: list[str] = Field(default_factory=list)
    informed: list[str] = Field(default_factory=list)


class NodeLinks(BaseModel):
    raci: Raci = Field(default_factory=Raci)
    check_ids: list[str] = Field(default_factory=list)
    time_constraint_ids: list[str] = Field(default_factory=list)
    permission_ids: list[str] = Field(default_factory=list)
    exception_ids: list[str] = Field(default_factory=list)
    required_evidence: list[EvidenceRequirement] = Field(default_factory=list)
    assertion: Optional[Assertion] = None


class EdgeLinks(BaseModel):
    time_constraint_id: Optional[str] = None
    exception_id: Optional[str] = None
    assertion: Optional[Assertion] = None


class OntologyView(BaseModel):
    schema_version: Literal["3.0"] = "3.0"
    ontology: Ontology
    node_links: dict[str, NodeLinks] = Field(default_factory=dict)
    edge_links: dict[str, EdgeLinks] = Field(default_factory=dict)


# Registry field name -> id field name on its items, shared with ontology_validator.
REGISTRY_ID_FIELDS: dict[str, str] = {
    "roles": "role_id",
    "checks": "check_id",
    "time_constraints": "time_constraint_id",
    "permissions": "permission_id",
    "exception_cases": "exception_id",
    "escalation_policies": "policy_id",
    "scopes": "scope_id",
    "evidence": "evidence_id",
}

DEFAULT_SCOPE_ID = "scope_default"

_CRITERION_KIND = {
    "metric": "numeric", "numeric_range": "numeric",
    "categorical": "categorical", "boolean": "boolean", "text": "text",
}
_SLA_KIND = {"deadline": "deadline", "target": "target", "warn_threshold": "warn_threshold"}
_V2_BANDS = ("normal", "warning", "critical")

# "15-35" / "15~35" / "15 至 35"
_RANGE_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(?:-|~|～|至|到)\s*(-?\d+(?:\.\d+)?)\s*(\S*)\s*$")
# ">= 1.33" / "≥1.33" / "< 2°C" / "> 50%"
_BOUND_RE = re.compile(r"^\s*(>=|<=|≥|≤|>|<)\s*(-?\d+(?:\.\d+)?)\s*(\S*)\s*$")


def parse_threshold_text(text: Any) -> Optional[tuple[dict[str, Any], Optional[str]]]:
    """Best-effort parse of a v2 free-text threshold into (LimitBand kwargs minus `band`, unit).
    Returns None when the text isn't one of the simple forms above -- the caller then keeps the
    original only in `limits_text`, rather than guessing."""
    if not isinstance(text, str):
        return None
    m = _RANGE_RE.match(text)
    if m:
        lo, hi, unit = float(m.group(1)), float(m.group(2)), m.group(3) or None
        return {"lower": lo, "upper": hi}, unit
    m = _BOUND_RE.match(text)
    if m:
        op, val, unit = m.group(1), float(m.group(2)), m.group(3) or None
        if op in (">=", "≥"):
            return {"lower": val}, unit
        if op == ">":
            return {"lower": val, "lower_inclusive": False}, unit
        if op in ("<=", "≤"):
            return {"upper": val}, unit
        return {"upper": val, "upper_inclusive": False}, unit
    return None


def _node_assertion(node: dict[str, Any]) -> Assertion:
    """confidence_basis for a collected node: expert_confirmed beats everything; otherwise a node
    backed by a verbatim expert quote is expert_stated; anything else was inferred by the model."""
    if node.get("expert_confirmed"):
        basis: ConfidenceBasis = "expert_confirmed"
    elif node.get("evidence"):
        basis = "expert_stated"
    else:
        basis = "llm_inferred"
    return Assertion(
        confidence=node.get("confidence"),
        confidence_basis=basis,
        expert_confirmed=bool(node.get("expert_confirmed")),
        source_turn_ids=list(node.get("source_turn_ids") or []),
    )


def _role_id(name: str) -> str:
    return f"role_{name}"


class _Builder:
    """Accumulates lifted objects; skips ids that the explicit v3 block already registered."""

    def __init__(self, explicit: Ontology):
        self.ont = explicit.model_copy(deep=True)
        self._ids = {
            reg: {getattr(o, idf) for o in getattr(self.ont, reg)}
            for reg, idf in REGISTRY_ID_FIELDS.items()
        }

    def add(self, registry: str, obj: BaseModel) -> str:
        oid = getattr(obj, REGISTRY_ID_FIELDS[registry])
        if oid not in self._ids[registry]:
            getattr(self.ont, registry).append(obj)
            self._ids[registry].add(oid)
        return oid

    def role(self, name: str) -> str:
        return self.add("roles", Role(role_id=_role_id(name), name=name))


def _merge_unique(dst: list, src: list) -> None:
    for x in src:
        if x not in dst:
            dst.append(x)


def lift_v2_record(record: dict[str, Any]) -> OntologyView:
    """Project a stored workflow record (v2 / Phase 3-A fields, optionally with explicit v3
    `ontology` + node link fields) into the ontology view. Deterministic and side-effect free."""
    graph = record.get("graph") or {}
    b = _Builder(Ontology.model_validate(record.get("ontology") or {}))

    # Record-level manufacturing_context -> default applicability scope.
    ctx = record.get("manufacturing_context") or {}
    selectors = {k: [v] for k, v in ctx.items() if isinstance(v, str) and v}
    b.add("scopes", Scope(scope_id=DEFAULT_SCOPE_ID, name="默认范围（由 manufacturing_context 生成）",
                          selectors=selectors))

    node_links: dict[str, NodeLinks] = {}
    for node in graph.get("nodes", []):
        nid = node["node_id"]
        # Explicit v3 link fields on the node are taken as-is, lifted links are merged in after.
        links = NodeLinks.model_validate({
            k: node[k] for k in (
                "raci", "check_ids", "time_constraint_ids", "permission_ids",
                "exception_ids", "required_evidence", "assertion",
            ) if node.get(k) is not None
        })
        if links.assertion is None:
            links.assertion = _node_assertion(node)

        # Roles -> RACI responsible.
        _merge_unique(links.raci.responsible, [b.role(r) for r in node.get("actor_roles") or [] if r])

        # Expert quotes -> provenance evidence.
        for i, quote in enumerate(node.get("evidence") or []):
            ev_id = b.add("evidence", Evidence(
                evidence_id=f"ev_{nid}_{i + 1}", kind="expert_quote", content=quote,
                turn_id=(node.get("source_turn_ids") or [None])[0],
            ))
            _merge_unique(links.assertion.evidence_ids, [ev_id])

        # evaluation_criteria -> Check (threshold + expected value).
        for crit in node.get("evaluation_criteria") or []:
            limits: list[LimitBand] = []
            unit = crit.get("unit")
            thresholds = crit.get("thresholds") or {}
            for band in _V2_BANDS:
                parsed = parse_threshold_text(thresholds.get(band))
                if parsed:
                    kwargs, parsed_unit = parsed
                    limits.append(LimitBand(band=band, **kwargs))
                    unit = unit or parsed_unit
            chk_id = b.add("checks", Check(
                check_id=f"chk_{nid}_{crit['id']}",
                name=crit.get("name") or crit["id"],
                kind=_CRITERION_KIND.get(crit.get("type"), "text"),
                unit=unit,
                limits=limits,
                limits_text=thresholds or None,
                allowed_values=list(crit.get("allowed_values") or []),
                aggregation=crit.get("aggregation"),
                source_criterion_id=crit["id"],
            ))
            _merge_unique(links.check_ids, [chk_id])

        # sla_config / expected_duration -> TimeConstraint (+ escalation policy stub).
        sla = node.get("sla_config")
        if sla:
            on_violation = None
            action = sla.get("violation_action")
            if action:
                on_violation = ViolationHandling(action=action)
                if action == "escalate":
                    on_violation.escalation_policy_id = b.add("escalation_policies", EscalationPolicy(
                        policy_id=f"esc_{nid}_sla", name=f"{node.get('label', nid)} 超时升级",
                        trigger=EscalationTrigger(kind="timeout"),
                        # Who it escalates to is not in v2 -- left empty on purpose so the
                        # validator asks for it instead of us inventing a manager.
                        levels=[EscalationLevel(level=1)],
                    ))
            tc_id = b.add("time_constraints", TimeConstraint(
                time_constraint_id=f"tc_{nid}_sla",
                kind=_SLA_KIND.get(sla.get("type"), "deadline"),
                duration=sla.get("duration"),
                anchor=sla.get("from_trigger"),
                enforced=sla.get("enforced"),
                on_violation=on_violation,
                description=sla.get("description"),
            ))
            _merge_unique(links.time_constraint_ids, [tc_id])
        if node.get("expected_duration"):
            tc_id = b.add("time_constraints", TimeConstraint(
                time_constraint_id=f"tc_{nid}_expected", kind="expected_duration",
                duration=node["expected_duration"], anchor="node_started",
            ))
            _merge_unique(links.time_constraint_ids, [tc_id])

        # approval_matrix -> Permission (action=approve) (+ escalation on rejection).
        for i, row in enumerate(node.get("approval_matrix") or []):
            esc_id = None
            if row.get("escalation_level"):
                esc_id = b.add("escalation_policies", EscalationPolicy(
                    policy_id=f"esc_{nid}_approval_{i + 1}",
                    trigger=EscalationTrigger(kind="rejection"),
                    levels=[EscalationLevel(level=int(row["escalation_level"]), action="approval_required")],
                ))
            perm_id = b.add("permissions", Permission(
                permission_id=f"perm_{nid}_{i + 1}",
                action="approve",
                allowed_role_ids=[b.role(r) for r in row.get("required_roles") or [] if r],
                sequence=row.get("sequence"),
                submission_criteria=(
                    [SubmissionCriterion(kind="object_state", description=row["criteria"])]
                    if row.get("criteria") else []
                ),
                escalation_policy_id=esc_id,
            ))
            _merge_unique(links.permission_ids, [perm_id])

        # retry_semantics temporary measure / containment_scope -> ExceptionCase.
        retry = node.get("retry_semantics") or {}
        containment = node.get("containment_scope")
        if retry.get("is_temporary") or containment:
            esc_id = None
            repeat = retry.get("escalation_on_repeat") or {}
            if repeat.get("enabled"):
                action = repeat.get("action")
                esc_id = b.add("escalation_policies", EscalationPolicy(
                    policy_id=f"esc_{nid}_repeat", name=f"{node.get('label', nid)} 重复发生升级",
                    trigger=EscalationTrigger(kind="repeat", description=repeat.get("trigger")),
                    levels=[EscalationLevel(
                        level=1,
                        action="create_capa" if action == "create_capa"
                        else "stop_production" if action == "stop_production" else "approval_required",
                    )],
                    terminal_action=action,
                ))
            temp = None
            if retry.get("is_temporary"):
                temp = {
                    "description": retry.get("description") or retry.get("condition"),
                    "expiration": retry.get("expiration"),
                    "revocation_trigger": retry.get("revocation_trigger"),
                }
            exc_id = b.add("exception_cases", ExceptionCase(
                exception_id=f"exc_{nid}",
                name=retry.get("condition") or f"{node.get('label', nid)} 异常",
                trigger=ExceptionTrigger(kind="event", description=retry.get("condition")),
                containment=containment,
                temporary_measure=temp,
                escalation_policy_id=esc_id,
            ))
            _merge_unique(links.exception_ids, [exc_id])

        node_links[nid] = links

    # Edges: exception_forward -> ExceptionCase handled at the edge's target; timeout -> links
    # to the source node's deadline-ish time constraint.
    edge_links: dict[str, EdgeLinks] = {}
    for edge in graph.get("edges", []):
        eid, src = edge["edge_id"], edge["from"]
        el = EdgeLinks(
            time_constraint_id=edge.get("time_constraint_id"),
            exception_id=edge.get("exception_id"),
            assertion=Assertion(
                confidence=edge.get("confidence"),
                confidence_basis="expert_confirmed" if edge.get("expert_confirmed") else "llm_inferred",
                expert_confirmed=bool(edge.get("expert_confirmed")),
                source_turn_ids=list(edge.get("source_turn_ids") or []),
            ),
        )
        src_links = node_links.get(src)
        if edge.get("edge_type") == "exception_forward" and not el.exception_id:
            el.exception_id = b.add("exception_cases", ExceptionCase(
                exception_id=f"exc_{eid}",
                name=edge.get("condition") or edge.get("label"),
                trigger=ExceptionTrigger(kind="event", description=edge.get("condition")),
                handler_node_id=edge["to"],
                containment=edge.get("containment_scope"),
            ))
            if src_links:
                _merge_unique(src_links.exception_ids, [el.exception_id])
        if edge.get("edge_type") == "timeout" and not el.time_constraint_id:
            existing = src_links.time_constraint_ids[0] if src_links and src_links.time_constraint_ids else None
            el.time_constraint_id = existing or b.add("time_constraints", TimeConstraint(
                time_constraint_id=f"tc_{eid}", kind="deadline", anchor="node_started",
                description=edge.get("condition"),
            ))
            if src_links:
                _merge_unique(src_links.time_constraint_ids, [el.time_constraint_id])
        edge_links[eid] = el

    return OntologyView(ontology=b.ont, node_links=node_links, edge_links=edge_links)
