"""Pydantic models mirroring docs/expert-workflow-collection/schema/workflow_graph_schema_v2.json,
scoped to what Phase 1 (PRD IMPLEMENTATION_PLAN.md) actually needs: the expert collection session
and the DAG it produces. Dataset/Dashboard/Experiment-center records are out of scope for this phase.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

NodeType = Literal[
    "start", "activity", "decision", "parallel_split", "parallel_join",
    "merge", "approval", "handoff", "wait", "end",
]

EdgeType = Literal[
    "normal", "conditional", "parallel", "merge", "handoff", "approval",
    "timeout", "exception_forward",
]

WorkflowStatus = Literal["draft", "collecting", "needs_confirmation", "expert_confirmed"]


class RetrySemantics(BaseModel):
    enabled: bool = True
    rework_reference_node_id: Optional[str] = None
    condition: Optional[str] = None
    description: Optional[str] = None


class Node(BaseModel):
    node_id: str
    node_type: NodeType
    label: str
    actor_roles: list[str] = Field(default_factory=list)
    decision_question: Optional[str] = None
    confidence: float = 1.0
    expert_confirmed: bool = False
    source_turn_ids: list[str] = Field(default_factory=list)
    retry_semantics: Optional[RetrySemantics] = None
    # Free-form layout hint; React Flow fills this in, the backend just round-trips it
    # untouched (PRD 11.4: keep manual_position across re-layouts).
    manual_position: Optional[dict] = None


class Edge(BaseModel):
    edge_id: str
    from_: str = Field(alias="from")
    to: str
    edge_type: EdgeType
    condition: Optional[str] = None
    confidence: float = 1.0
    expert_confirmed: bool = False
    source_turn_ids: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class Graph(BaseModel):
    graph_type: Literal["dag"] = "dag"
    start_node_ids: list[str] = Field(default_factory=list)
    end_node_ids: list[str] = Field(default_factory=list)
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)


class ConversationTurn(BaseModel):
    turn_id: str
    role: Literal["expert", "assistant"]
    # Full plain text of the message -- what exports/anonymization/older records read.
    text: str
    # Assistant turns only, all optional (older records don't have them): the same message
    # split into layers so the chat bubble can render them separately -- a short restatement
    # of what was just recorded, the one question being asked, a one-line "why ask this",
    # and the chips that were offered with it (kept so the history shows what was picked).
    ack: Optional[str] = None
    question: Optional[str] = None
    why: Optional[str] = None
    chips: Optional[list[str]] = None
    chip_mode: Optional[Literal["prefill", "multi_select"]] = None


class NextQuestion(BaseModel):
    target: str
    priority: str
    question: str
    # None means no chips: this is a recall-type question (PRD section 18).
    chips: Optional[list[str]] = None
    # "prefill" (default/omitted, existing behavior): clicking a chip fills the whole draft
    # box, single choice. "multi_select": chips toggle on/off, expert confirms the combined
    # selection before it goes into the draft box (IMPLEMENTATION_PLAN.md section 9.1,
    # Case Context B-group). Never auto-sends either way -- PRD section 18 still applies.
    chip_mode: Optional[Literal["prefill", "multi_select"]] = None
    # Restatement of what was just recorded, and a one-line reason for asking (see
    # guide_phrasing.py). Both optional -- rendered as separate layers of the bubble.
    ack: Optional[str] = None
    why: Optional[str] = None


class ValidationIssue(BaseModel):
    level: Literal["error", "warning"]
    code: str
    message: str
    node_id: Optional[str] = None
    edge_id: Optional[str] = None


class Completion(BaseModel):
    score: float
    ready_for_confirmation: bool


class WorkflowSummary(BaseModel):
    id: str
    name: str
    status: WorkflowStatus
    completion_score: float
    updated_at: str


ManufacturingMode = Literal[
    "mass_repetitive", "high_automation", "high_mix_low_volume", "eto_mto",
    "large_project", "regulated_traceable", "other",
]


class ManufacturingContext(BaseModel):
    """§14.4 Dataset Slice -- mirrors `manufacturing_context` in
    schema/workflow_graph_schema_v2.json's `workflow_record` def verbatim (field names and the
    `manufacturing_mode` enum), not an invented taxonomy: `public_extracted` imports already
    require this object and `import_pipeline.py` already validates `manufacturing_mode`
    against this enum, it just wasn't read by anything downstream yet. `expert_collected`
    gets the same shape as an optional, editable-anytime tag (not collected through the FSM
    conversation -- it's a static classification, not scenario narrative) so both source types
    can be sliced by the same fields.
    """
    manufacturing_mode: Optional[ManufacturingMode] = None
    industry: Optional[str] = None
    site_type: Optional[str] = None
    process_area: Optional[str] = None
    product_family: Optional[str] = None
    shift_context: Optional[str] = None


class ManufacturingContextUpdateRequest(BaseModel):
    manufacturing_mode: Optional[ManufacturingMode] = None
    industry: Optional[str] = None
    site_type: Optional[str] = None
    process_area: Optional[str] = None
    product_family: Optional[str] = None
    shift_context: Optional[str] = None


class CaseContext(BaseModel):
    """Scenario (A-group) + Case Context (B-group) -- IMPLEMENTATION_PLAN.md section 9.1.
    All fields optional/empty-default because this fills in gradually turn by turn; a
    workflow record mid-collection legitimately has a partially-filled CaseContext.
    """
    scenario_trigger: Optional[str] = None
    scenario_goal: Optional[str] = None
    scenario_success: Optional[str] = None
    known_info: Optional[str] = None
    unknown_info: Optional[str] = None
    constraints: Optional[str] = None
    available_resources: Optional[str] = None
    # PRD 18.2 P6: where the expert relied on experience rather than written rules.
    experience_notes: Optional[str] = None
    # A-group: which fields the expert answered in "brief" vs "detailed" mode.
    detail_level: dict[str, str] = Field(default_factory=dict)
    # B-group: which fields the expert skipped by picking the "无" chip.
    skipped_fields: list[str] = Field(default_factory=list)


class WorkflowRecord(BaseModel):
    id: str
    name: str
    status: WorkflowStatus
    stage: str
    graph: Graph
    turns: list[ConversationTurn]
    unresolved: list[NextQuestion]
    completion: Completion
    validation: list[ValidationIssue] = Field(default_factory=list)
    case_context: Optional[CaseContext] = None
    manufacturing_context: Optional[ManufacturingContext] = None
    created_at: str
    updated_at: str


class CreateWorkflowRequest(BaseModel):
    name: Optional[str] = None


class TurnRequest(BaseModel):
    text: str


class TurnResponse(BaseModel):
    assistant_reply: str
    graph_ops_applied: int
    current_dag: Graph
    completion: Completion
    validation: list[ValidationIssue]
    next_question: Optional[NextQuestion] = None


# --- Dataset / Dashboard (PRD 12/13, Phase 3 sub-scope -- see IMPLEMENTATION_PLAN.md section 6) ---

SourceType = Literal["expert_collected", "public_extracted"]


class DimensionScore(BaseModel):
    score: Optional[float] = None
    band: str
    sub_indicators: dict
    scope_note: str
    explanation: str = ""


class DatasetReadiness(BaseModel):
    overall: Optional[float] = None
    band: str
    sample_size: int
    dimensions: dict[str, DimensionScore]


class DatasetVersionSummary(BaseModel):
    id: str
    source_type: SourceType
    version_number: int
    workflow_count: int
    total_steps: int
    microflow_count: Optional[int] = None
    created_at: str
    readiness: DatasetReadiness
    archived: bool = False
    is_gold: bool = False


class PublishDatasetRequest(BaseModel):
    source_type: SourceType = "expert_collected"
    name: Optional[str] = None
    actor_role: Optional[str] = None


class ImportConfirmRequest(BaseModel):
    payload: dict
    name: Optional[str] = None
    actor_role: Optional[str] = None
    import_records_without_errors: bool = False


# --- Duplicate check (IMPLEMENTATION_PLAN.md section 10) ---
# Standalone from precheck/import so it can be called on its own -- e.g. to inspect a file's
# relationship to the existing corpus before deciding whether to fix and re-upload it.

DuplicateKind = Literal["duplicate", "microflow_reuse_candidate", "content_match_structure_diff"]


class DuplicateCheckRequest(BaseModel):
    payload: dict  # same {dataset_meta, records[]} shape as import


class DuplicateMatch(BaseModel):
    record_id: str
    matched_record_id: str
    matched_version_number: Optional[int] = None  # None for a within-batch match
    text_similarity: float
    structure_similarity: float
    kind: DuplicateKind


class DuplicateCheckResult(BaseModel):
    source_type: SourceType
    total_records: int
    # "duplicate" = same scenario AND same structure, definitionally a repeat.
    # "microflow_reuse_candidate" = different scenario, similar structure -- likely the same
    # reusable micro-workflow recurring, not a data-quality problem.
    duplicates: list[DuplicateMatch]
    reuse_candidates: list[DuplicateMatch]
    other_matches: list[DuplicateMatch]  # content_match_structure_diff, rare edge case


# --- Prior annotation (Phase 7 sub-phase B, IMPLEMENTATION_PLAN.md section 9.2) ---
# "Public/LLM-derived Prior -> Expert-annotated Prior" from the design draft: any single
# annotation flips this, unchanged since Phase 7 (design draft decision 3).
#
# --- Gold annotation (IMPLEMENTATION_PLAN.md section 9, §9 Phase C-2): a stricter status
# layered on top, requiring two independent annotations that agree (or a third person's
# arbitration when they don't) -- see gold_status below and _compute_gold_status in
# routers/annotations.py. Applies to both public_extracted and expert_collected versions now
# (decision: both need Gold, not just imports).

PriorStatus = Literal["raw", "expert_annotated"]
PriorVerdict = Literal["accepted", "needs_revision", "rejected"]
GoldStatus = Literal["not_gold", "pending_second_review", "disputed_pending_arbitration", "gold"]
AnnotationRole = Literal["independent", "arbitration"]
# Per-node judgement string: "keep" / "delete" / "merge_into:<other_node_id>".
NodeVerdicts = dict[str, str]


class CreateAnnotationRequest(BaseModel):
    verdict: PriorVerdict
    node_verdicts: NodeVerdicts = Field(default_factory=dict)
    note: Optional[str] = None
    actor_role: Optional[str] = None
    # Required (not just an audit nicety): without a real account system, this is the only
    # signal routers/annotations.py has to tell two independent annotators apart -- see
    # IMPLEMENTATION_PLAN.md section 9's note on this limitation.
    annotator_name: str


class PriorAnnotation(BaseModel):
    annotation_id: str
    version_id: str
    record_id: str
    based_on_annotation_id: Optional[str] = None
    verdict: PriorVerdict
    node_verdicts: NodeVerdicts = Field(default_factory=dict)
    note: Optional[str] = None
    actor_role: Optional[str] = None
    annotator_name: str
    role_in_process: AnnotationRole = "independent"
    annotated_at: str


class PriorRecordDetail(BaseModel):
    record_id: str
    name: str
    # Loosely typed, not `Graph`: public_extracted records (this model's only use case) are
    # treated as raw dicts everywhere else in the codebase too (import_pipeline.py,
    # datasets.py's _records_for_export) because imported data can carry a graph_type the
    # strict internal Graph model doesn't accept (e.g. the sample data's "directed_graph"
    # vs. the model's "dag") -- graph_validator.py already validates structure without
    # requiring that literal match, so re-imposing it here would reject data the rest of
    # the import pipeline already accepted.
    graph: dict
    prior_status: PriorStatus
    gold_status: GoldStatus = "not_gold"
    annotations: list[PriorAnnotation] = Field(default_factory=list)  # oldest first


class PriorRecordSummary(BaseModel):
    record_id: str
    name: str
    node_count: int
    prior_status: PriorStatus
    latest_verdict: Optional[PriorVerdict] = None
    gold_status: GoldStatus = "not_gold"


class AnnotationSummary(BaseModel):
    version_id: str
    total_records: int
    annotated_records: int
    verdict_counts: dict[str, int]
    gold_counts: dict[str, int] = Field(default_factory=dict)
    agreement_kappa: Optional[float] = None


# --- Experiment Center (PRD 14, Phase 4 sub-scope -- see IMPLEMENTATION_PLAN.md section 7) ---

ExperimentMethod = Literal["consensus_dfg", "pm4py_inductive", "pm4py_heuristics", "llm_extractor"]
ExperimentStatus = Literal["queued", "running", "completed", "failed"]
Representation = Literal["sequence_projection", "node_edge_graph", "event_log", "text_serialization"]
InputVersion = Literal["raw", "anonymized", "role_normalized"]


class CreateExperimentRequest(BaseModel):
    name: str
    source_type: SourceType = "expert_collected"
    dataset_version_id: str
    input_version: InputVersion = "raw"
    representation: Representation = "node_edge_graph"
    method: ExperimentMethod = "consensus_dfg"
    model_name: Optional[str] = None  # only meaningful when method == "llm_extractor"
    prompt_version: Optional[str] = None
    temperature: Optional[float] = None
    seed: int = 42
    train_split: float = 0.7
    gold_nodes: bool = False
    gold_edges: bool = False
    gold_boundary: bool = False
    gold_roles: bool = False
    actor_role: Optional[str] = None


class ExperimentSummary(BaseModel):
    id: str
    name: str
    dataset_version_id: str
    dataset_label: str
    method: ExperimentMethod
    model_name: Optional[str] = None
    status: ExperimentStatus
    created_by: str
    created_at: str
    node_f1: Optional[float] = None
    graph_structural_f1: Optional[float] = None


class ExperimentDetail(ExperimentSummary):
    source_type: SourceType
    input_version: InputVersion
    representation: Representation
    prompt_version: Optional[str] = None
    temperature: Optional[float] = None
    seed: int
    train_split: float
    train_count: Optional[int] = None
    test_count: Optional[int] = None
    metrics: dict = Field(default_factory=dict)
    explanation: Optional[str] = None
    explanation_edited: bool = False
    consensus_graph: Optional[Graph] = None
    error_analysis: list[dict] = Field(default_factory=list)
    error_clusters: list[dict] = Field(default_factory=list)
    failure_reason: Optional[str] = None


class ExplanationUpdateRequest(BaseModel):
    text: str


class ComparisonRequest(BaseModel):
    experiment_ids: list[str]


class ComparisonResult(BaseModel):
    experiments: list[ExperimentSummary]
    metric_table: dict
    narrative: str
