"""Pydantic models mirroring docs/expert-workflow-collection/schema/workflow_graph_schema_v2.json,
scoped to what Phase 1 (PRD IMPLEMENTATION_PLAN.md) actually needs: the expert collection session
and the DAG it produces. Dataset/Dashboard/Experiment-center records are out of scope for this phase.
"""
from __future__ import annotations

from typing import Literal, Optional, Union

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
    # Section 17: verbatim quote(s) from what the expert/annotator said that back this step.
    # Empty for steps the model couldn't tie to a quote -- those are asked about first.
    evidence: list[str] = Field(default_factory=list)
    # Free-form layout hint; React Flow fills this in, the backend just round-trips it
    # untouched (PRD 11.4: keep manual_position across re-layouts).
    manual_position: Optional[dict] = None
    # Stable, human-facing step number ("第3步") -- assigned once at creation
    # (graph_ops.assign_missing_seqs) and never renumbered afterward, so it stays a reliable
    # natural-language handle for the review loop across a whole conversation. None only for
    # data collected before this field existed and not yet backfilled.
    seq: Optional[int] = None
    # Phase 3-A (#34) / ontology follow-up fields (docs/expert-workflow-collection/ontology/).
    # Kept as plain dicts mirroring workflow_graph_schema_v3.json so the API returns them
    # untouched; app.ontology owns their typed reading.
    evaluation_criteria: list[dict] = Field(default_factory=list)
    sla_config: Optional[dict] = None
    approval_matrix: list[dict] = Field(default_factory=list)
    containment_scope: Optional[dict] = None


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
    # Expert turns: raw speech-recognition output if dictated (section 17.5).
    raw_transcript: Optional[str] = None
    # Assistant turns only, all optional (older records don't have them): the same message
    # split into layers so the chat bubble can render them separately -- a short restatement
    # of what was just recorded, the one question being asked, a one-line "why ask this",
    # and the chips that were offered with it (kept so the history shows what was picked).
    ack: Optional[str] = None
    question: Optional[str] = None
    why: Optional[str] = None
    # Review-loop assistant turns (section 17): concrete graph changes made this turn, a
    # multi-line body (read-back / notices), and the sample narration on the opening message.
    changes: Optional[list[str]] = None
    body: Optional[str] = None
    sample: Optional[str] = None
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
    # Session-list housekeeping (left rail "..." menu). Archive, not delete: an archived
    # session is only hidden from the default list and excluded from the dataset draft pool --
    # its record stays in the DB, because a published expert_collected dataset_version only
    # stores workflow_ids and reads each graph back live (dataset_records.records_for_export),
    # so hard-deleting a workflow would silently drop records out of an already-published
    # version.
    pinned: bool = False
    archived: bool = False
    # Soft delete (the session list's 「已删除」 tab): hidden from every other tab and from the
    # dataset draft pool, restorable. Never a hard delete -- see the note above.
    deleted: bool = False
    # True once any dataset_version (archived versions included) references this workflow --
    # computed at read time from dataset_versions, never stored on the workflow itself.
    in_dataset: bool = False


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


TaskDefinitionSource = Literal["expert_defined", "llm_mined", "org_inferred"]


class TaskDefinition(BaseModel):
    """One Task node's link down into the step (SOP) graph -- IMPLEMENTATION_PLAN.md section 18.
    Name/owner are NOT here: they live on the matching TaskWorkflow.graph node (`label` /
    `actor_roles`), so export anonymization, which already walks node labels and roles, covers
    them without a second set of rules.
    """
    task_id: str  # == the node_id of this task in TaskWorkflow.graph
    # Which nodes of WorkflowRecord.graph (the SOP / step graph) make up this task's internal
    # workflow. Empty when the expert named the task but never described its steps.
    sop_node_ids: list[str] = Field(default_factory=list)
    # Product-owner priority for where a task layer may come from: expert_defined (the only
    # one produced this iteration) > llm_mined (from real work logs, future) > org_inferred
    # (auxiliary hint only, never allowed to define the DAG alone).
    definition_source: TaskDefinitionSource = "expert_defined"
    # Whether the expert's outline was split into items by the real LLM or the rule fallback.
    structured_by: Literal["llm", "rule"] = "rule"


class TaskWorkflow(BaseModel):
    """Upper layer of the dual-DAG model ("谁负责哪一段"); `WorkflowRecord.graph` stays the step
    graph ("每一段怎么做"). Kept as its own plain Graph so DagView/validator/export reuse it.
    """
    graph: Graph
    tasks: list[TaskDefinition] = Field(default_factory=list)


class WorkflowRecord(BaseModel):
    id: str
    name: str
    status: WorkflowStatus
    stage: str
    # The step-level graph -- in dual-DAG terms, the SOP / Skill DAG. Name kept as `graph` so
    # every existing consumer (datasets, experiments, quality scoring) is unchanged.
    graph: Graph
    turns: list[ConversationTurn]
    unresolved: list[NextQuestion]
    completion: Completion
    validation: list[ValidationIssue] = Field(default_factory=list)
    case_context: Optional[CaseContext] = None
    # None for sessions collected before the task layer existed, and until the expert answers
    # the task-outline question at the end of the conversation.
    task_workflow: Optional[TaskWorkflow] = None
    manufacturing_context: Optional[ManufacturingContext] = None
    created_at: str
    updated_at: str
    pinned: bool = False
    archived: bool = False
    deleted: bool = False
    in_dataset: bool = False


class WorkflowMetaUpdateRequest(BaseModel):
    """PATCH body for the session-list "..." menu (rename / pin / archive). Every field is
    optional; only the ones actually sent are applied.
    """
    name: Optional[str] = None
    pinned: Optional[bool] = None
    archived: Optional[bool] = None
    deleted: Optional[bool] = None


class NodePositionUpdateRequest(BaseModel):
    """PATCH body for a manual node drag -- the only path that can ever move a node (see
    Node.manual_position; review_agent.sanitize_ops's update_node patch whitelist never
    includes position, so an LLM-driven edit cannot reach this)."""
    x: float
    y: float


class DatasetVersionRef(BaseModel):
    id: str
    source_type: str
    version_number: int
    archived: bool = False


class RegenerateGraphCheck(BaseModel):
    """Pre-flight answer for "用大模型根据会话内容重新生成流程图" -- the frontend asks this
    first and shows `reason` instead of a confirm dialog when `allowed` is False.
    """
    allowed: bool
    # "in_dataset" | "conversation_in_progress" | "no_expert_turns" | None when allowed
    blocked_code: Optional[str] = None
    reason: Optional[str] = None
    dataset_versions: list[DatasetVersionRef] = Field(default_factory=list)
    # Regenerating a confirmed workflow drops it back to needs_confirmation -- surfaced so the
    # confirm dialog can warn about it up front.
    will_reset_confirmation: bool = False


class CreateWorkflowRequest(BaseModel):
    name: Optional[str] = None


class TurnRequest(BaseModel):
    text: str
    # Raw speech-recognition output when the expert dictated this message (section 17.5);
    # `text` is what they actually sent after editing.
    raw_transcript: Optional[str] = None


class SpeechPolishRequest(BaseModel):
    text: str


class SpeechPolishResponse(BaseModel):
    text: str
    # False whenever the LLM step was skipped or failed (slot disabled/not configured, or any
    # llm_client.LLMError) -- `text` is then the untouched raw transcript, not a fabricated
    # "polished" result. Lets the frontend show a subtle "AI 未整理，原始识别结果" hint instead
    # of silently claiming a cleanup that didn't happen.
    polished: bool


class TurnResponse(BaseModel):
    assistant_reply: str
    graph_ops_applied: int
    current_dag: Graph
    completion: Completion
    validation: list[ValidationIssue]
    next_question: Optional[NextQuestion] = None
    # The full record after this turn (C3) -- lets the client update both the open session and its
    # row in the session list without two more requests. Optional only for older clients/tests.
    record: Optional["WorkflowRecord"] = None


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
    name: str
    version_number: int
    workflow_count: int
    total_steps: int
    microflow_count: Optional[int] = None
    created_at: str
    readiness: DatasetReadiness
    archived: bool = False
    is_gold: bool = False


class DatasetVersionListResponse(BaseModel):
    """Dashboard's「全部」数据集列表 -- paginated + searchable, distinct from the plain
    `list[DatasetVersionSummary]` `/versions` already returns (that one stays a flat list
    since existing callers -- the per-sourceType "latest version" read on the Dashboard
    landing view, the experiment center's version picker -- just want everything, unpaginated).
    """
    items: list[DatasetVersionSummary]
    total: int
    page: int
    page_size: int


class PublishDatasetRequest(BaseModel):
    source_type: SourceType = "expert_collected"
    name: Optional[str] = None
    actor_role: Optional[str] = None


class RenameDatasetVersionRequest(BaseModel):
    name: str
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
# What a record is waiting for -- drives the annotation queue/filters (gold_annotation.py).
# Section 17 removed section 16's separate "rework" stage.
AnnotationStage = Literal["first_review", "second_review", "arbitration", "done"]
# Per-node judgement string: "keep" / "delete" / "merge_into:<predecessor_node_id>".
NodeVerdicts = dict[str, str]
# Structured reasons for "needs_revision"/"rejected" (decision 10: fixed tags so the
# distribution can be counted, instead of free text only). Labels live in the frontend's
# REASON_TAG_LABELS; `note` stays as an optional free-text supplement ("other" requires it).
ReasonTag = Literal[
    "missing_step", "extra_step", "wrong_order", "duplicate", "wrong_branch",
    "wrong_role", "unclear_label", "out_of_scope", "other",
]


class CreateAnnotationRequest(BaseModel):
    verdict: PriorVerdict
    node_verdicts: NodeVerdicts = Field(default_factory=dict)
    reason_tags: list[ReasonTag] = Field(default_factory=list)
    note: Optional[str] = None
    actor_role: Optional[str] = None
    # Required (not just an audit nicety): without a real account system, this is the only
    # signal routers/annotations.py has to tell two independent annotators apart -- see
    # IMPLEMENTATION_PLAN.md section 9's note on this limitation.
    annotator_name: str
    # The round the annotator was looking at. When set and the record has since moved on
    # (someone else finished the round / submitted a rework), the submission is refused
    # with 409 instead of being silently attributed to a graph the annotator never saw.
    round: Optional[int] = None


class PriorAnnotation(BaseModel):
    annotation_id: str
    version_id: str
    record_id: str
    based_on_annotation_id: Optional[str] = None
    verdict: PriorVerdict
    node_verdicts: NodeVerdicts = Field(default_factory=dict)
    reason_tags: list[ReasonTag] = Field(default_factory=list)
    note: Optional[str] = None
    actor_role: Optional[str] = None
    annotator_name: str
    role_in_process: AnnotationRole = "independent"
    round: int = 1
    annotated_at: str
    # Section 17: annotations made in the review conversation carry the corrected graph
    # (needs_revision) and a plain-language list of what was changed.
    revised_graph: Optional[dict] = None
    changes: list[str] = Field(default_factory=list)
    session_id: Optional[str] = None


class ReworkEdits(BaseModel):
    """Section 16 rework edit set -- only kept so legacy `record_revisions` rows still load."""
    node_verdicts: NodeVerdicts = Field(default_factory=dict)
    renames: dict[str, str] = Field(default_factory=dict)
    inserts: list[dict] = Field(default_factory=list)


class RecordRevision(BaseModel):
    revision_id: str
    version_id: str
    record_id: str
    from_round: int  # the round whose "needs_revision" outcome this revision answers
    edits: ReworkEdits
    graph: dict  # the corrected graph this revision produced (what round from_round+1 reviews)
    reworker_name: str
    note: Optional[str] = None
    actor_role: Optional[str] = None
    created_at: str


class RecordSignal(BaseModel):
    """Machine-generated hint shown in the annotation panel (graph validator findings,
    near-duplicate / micro-workflow-reuse matches from import precheck). Not a human verdict,
    so it's visible even during blind independent review.
    """
    level: Literal["error", "warning"]
    code: str
    message: str
    node_id: Optional[str] = None


class PriorRecordDetail(BaseModel):
    record_id: str
    name: str
    # Loosely typed, not `Graph`: public_extracted records are treated as raw dicts everywhere
    # else in the codebase too (import_pipeline.py, dataset_records.py) because imported data
    # can carry a graph_type the strict internal Graph model doesn't accept (e.g. the sample
    # data's "directed_graph" vs. the model's "dag") -- graph_validator.py already validates
    # structure without requiring that literal match.
    # This is the record's *current* graph (the latest legacy rework revision's, else the
    # original). `final_graph` is the corrected graph a settled needs_revision outcome adopted.
    graph: dict
    original_graph: dict
    final_graph: Optional[dict] = None
    prior_status: PriorStatus
    gold_status: GoldStatus = "not_gold"
    stage: AnnotationStage = "first_review"
    round: int = 1
    # Blind review: while the record is in independent review (first/second_review), other
    # people's verdicts/notes/corrections are NOT returned -- only who has already annotated
    # this round (needed to stop the same person annotating twice) and, for legacy data, the
    # reworker's name. Everything is returned once the record reaches arbitration or done.
    blind: bool = False
    round_annotator_names: list[str] = Field(default_factory=list)
    round_reworker_name: Optional[str] = None
    annotation_count: int = 0
    annotations: list[PriorAnnotation] = Field(default_factory=list)  # oldest first; empty when blind
    revisions: list[RecordRevision] = Field(default_factory=list)  # oldest first; empty when blind
    final_verdict: Optional[PriorVerdict] = None  # only set when stage == "done"
    signals: list[RecordSignal] = Field(default_factory=list)


class PriorRecordSummary(BaseModel):
    record_id: str
    name: str
    node_count: int
    prior_status: PriorStatus
    # Only the settled outcome (stage == "done") -- an in-progress verdict would leak into
    # the next independent annotator's view from the list itself.
    final_verdict: Optional[PriorVerdict] = None
    gold_status: GoldStatus = "not_gold"
    stage: AnnotationStage = "first_review"
    round: int = 1
    round_annotator_names: list[str] = Field(default_factory=list)
    round_reworker_name: Optional[str] = None
    signal_error_count: int = 0
    signal_warning_count: int = 0


class StartReviewSessionRequest(BaseModel):
    annotator_name: str
    actor_role: Optional[str] = None


class ReviewSessionTurnRequest(BaseModel):
    text: str
    raw_transcript: Optional[str] = None


class ReviewSession(BaseModel):
    """One annotator's review conversation on one record (section 17.4). Blind: it only
    contains this annotator's own messages and their own working copy of the graph."""
    session_id: str
    version_id: str
    record_id: str
    annotator_name: str
    role_in_process: AnnotationRole
    round: int
    phase: str                      # review / final_confirm / done
    status: Literal["active", "submitted", "stale"]
    graph: dict                     # the annotator's working copy
    base_graph: dict                # what they started from
    turns: list[ConversationTurn] = Field(default_factory=list)
    proposal: Optional[dict] = None  # {verdict, reason_tags} while confirming
    annotation_id: Optional[str] = None  # set once submitted


class AnnotationSummary(BaseModel):
    version_id: str
    total_records: int
    annotated_records: int
    # Settled outcomes only (records at stage "done", plus rounds that ended in rework) --
    # counting in-progress verdicts would reveal them in aggregate on small versions.
    verdict_counts: dict[str, int]
    gold_counts: dict[str, int] = Field(default_factory=dict)
    stage_counts: dict[str, int] = Field(default_factory=dict)
    # How often each structured reason was given, across all non-accepted annotations.
    reason_tag_counts: dict[str, int] = Field(default_factory=dict)
    agreement_kappa: Optional[float] = None
    # Records settled with a corrected graph (needs_revision adopted), section 17.
    corrected_count: int = 0


# --- Experiment Center (PRD 14, Phase 4 sub-scope -- see IMPLEMENTATION_PLAN.md section 7) ---

ExperimentMethod = Literal["consensus_dfg", "pm4py_inductive", "pm4py_heuristics", "llm_extractor"]
ExperimentStatus = Literal["queued", "running", "completed", "failed"]
Representation = Literal["sequence_projection", "node_edge_graph", "event_log", "text_serialization"]
InputVersion = Literal["raw", "anonymized", "role_normalized"]


class CreateExperimentRequest(BaseModel):
    """No `source_type` field -- IMPLEMENTATION_PLAN.md's Combined Train design (PRD §14.1:
    "允许 Combined Train，Test 仍必须分别报告") means a single experiment's training pool can
    span multiple dataset versions across both source types, so a single top-level source_type
    would no longer describe the request. Each version's own `source_type` (read from
    `db.get_dataset_version`) is what the run actually groups train/test by; the frontend's
    "先筛一遍" source picker (PRD §12.0) is purely a UI convenience for narrowing the version
    checklist, not a field the backend needs.
    """
    name: str
    dataset_version_ids: list[str] = Field(min_length=1)
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
    dataset_version_ids: list[str]
    dataset_label: str
    source_types: list[SourceType]
    method: ExperimentMethod
    model_name: Optional[str] = None
    status: ExperimentStatus
    created_by: str
    created_at: str
    node_f1: Optional[float] = None
    graph_structural_f1: Optional[float] = None


class ExperimentDetail(ExperimentSummary):
    input_version: InputVersion
    representation: Representation
    prompt_version: Optional[str] = None
    temperature: Optional[float] = None
    seed: int
    train_split: float
    train_count: Optional[int] = None
    test_count: Optional[int] = None
    train_count_by_source: dict = Field(default_factory=dict)
    test_count_by_source: dict = Field(default_factory=dict)
    metrics: dict = Field(default_factory=dict)
    metrics_by_source: dict = Field(default_factory=dict)
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


# --- Phase 3-B: System Rules, Cross-workflow Relationships, Global Policies ---

# SystemRule: 系统级约束和政策
RuleType = Literal[
    "validation_constraint",      # 工作流验证约束
    "permission_requirement",     # 权限要求
    "resource_allocation",        # 资源分配规则
    "exception_handling",         # 异常处理规则
    "data_retention",            # 数据保留规则
    "compliance_requirement",    # 合规要求
]

RuleStatus = Literal["active", "deprecated", "draft", "archived"]


class SystemRule(BaseModel):
    """系统级规则：适用于工作流创建和修改的全局约束
    """
    rule_id: str
    rule_name: str
    rule_type: RuleType
    description: str
    status: RuleStatus = "active"

    # 规则内容和适用范围
    content: dict  # 规则具体内容，根据rule_type而异
    applicable_workflow_types: list[str] = Field(default_factory=list)  # 空表示全部
    applicable_stages: list[str] = Field(default_factory=list)  # workflow stages

    # 版本控制
    version: str  # semantic versioning
    effective_date: str  # RFC 3339
    expiry_date: Optional[str] = None  # RFC 3339，None表示永不过期

    # 元数据
    created_by: str
    created_at: str
    updated_by: str
    updated_at: str

    # 权限和审批
    requires_approval: bool = False
    approved_by: Optional[str] = None
    approval_date: Optional[str] = None

    # 影响分析
    estimated_affected_workflows: int = 0
    tags: list[str] = Field(default_factory=list)
    priority: Literal["low", "medium", "high", "critical"] = "medium"


class SystemRuleUpdate(BaseModel):
    """更新系统规则的请求体"""
    rule_name: Optional[str] = None
    description: Optional[str] = None
    content: Optional[dict] = None
    status: Optional[RuleStatus] = None
    applicable_workflow_types: Optional[list[str]] = None
    applicable_stages: Optional[list[str]] = None
    expiry_date: Optional[str] = None
    priority: Optional[Literal["low", "medium", "high", "critical"]] = None


# WorkflowRelationship: 工作流间的依赖和关系
RelationshipType = Literal[
    "dependency",           # A依赖B完成
    "data_handoff",        # A向B传递数据
    "parallel_split",      # A分裂为多个平行流程
    "merge",               # 多个流程合并为A
    "conditional",         # 条件依赖
    "resource_sharing",    # 共享资源
    "information_flow",    # 信息流动
]

ConstraintType = Literal[
    "time_constraint",     # 时间约束
    "resource_constraint", # 资源约束
    "data_constraint",     # 数据约束
    "sequence_constraint", # 顺序约束
]


class TimeConstraint(BaseModel):
    """时间约束"""
    constraint_type: Literal["time_constraint"] = "time_constraint"
    min_delay: Optional[int] = None  # 秒
    max_delay: Optional[int] = None  # 秒
    deadline: Optional[str] = None   # RFC 3339
    condition: Optional[str] = None  # 条件描述


class DataConstraint(BaseModel):
    """数据约束"""
    constraint_type: Literal["data_constraint"] = "data_constraint"
    required_fields: list[str] = Field(default_factory=list)
    data_format: Optional[str] = None
    validation_rule: Optional[str] = None


class WorkflowRelationship(BaseModel):
    """工作流间的依赖和关系"""
    relationship_id: str
    relationship_type: RelationshipType

    # 源和目标工作流
    source_workflow_id: str
    target_workflow_id: str

    # 关系描述
    description: str
    condition: Optional[str] = None  # 关系成立的条件

    # 约束
    constraints: list[Union[TimeConstraint, DataConstraint]] = Field(default_factory=list)

    # 版本和状态
    version: str
    status: RuleStatus = "active"

    # 元数据
    created_by: str
    created_at: str
    updated_by: str
    updated_at: str

    # 冲突检测标志
    has_circular_dependency: bool = False
    has_deadlock_risk: bool = False

    tags: list[str] = Field(default_factory=list)


class WorkflowRelationshipUpdate(BaseModel):
    """更新工作流关系的请求体"""
    description: Optional[str] = None
    condition: Optional[str] = None
    constraints: Optional[list[Union[TimeConstraint, DataConstraint]]] = None
    status: Optional[RuleStatus] = None


# GlobalPolicy: 全局策略和决策规则
PolicyScope = Literal[
    "organization",        # 组织级
    "department",         # 部门级
    "workflow_type",      # 工作流类型级
    "all",               # 全局
]

class DecisionRule(BaseModel):
    """决策规则"""
    rule_id: str
    rule_description: str
    condition: str  # 条件表达式
    action: str    # 采取的行动


class ExceptionHandler(BaseModel):
    """异常处理规则"""
    exception_type: str
    handling_strategy: str
    escalation_level: Literal["none", "manager", "director", "cto"]
    auto_remediation: bool = False
    remediation_action: Optional[str] = None


class GlobalPolicy(BaseModel):
    """全局策略：组织级、部门级或工作流类型级的决策规则"""
    policy_id: str
    policy_name: str
    description: str

    # 适用范围
    scope: PolicyScope
    scope_target: Optional[str] = None  # department_id / workflow_type

    # 策略内容
    decision_rules: list[dict] = Field(default_factory=list)
    exception_handlers: list[ExceptionHandler] = Field(default_factory=list)

    # 版本和状态
    version: str
    status: RuleStatus = "active"
    effective_date: str  # RFC 3339
    expiry_date: Optional[str] = None

    # 元数据
    created_by: str
    created_at: str
    updated_by: str
    updated_at: str

    # 审批流程
    requires_approval: bool = False
    approved_by: Optional[str] = None
    approval_date: Optional[str] = None

    # 关联的规则
    related_system_rules: list[str] = Field(default_factory=list)
    related_relationships: list[str] = Field(default_factory=list)

    priority: Literal["low", "medium", "high", "critical"] = "medium"
    tags: list[str] = Field(default_factory=list)


class GlobalPolicyUpdate(BaseModel):
    """更新全局策略的请求体"""
    policy_name: Optional[str] = None
    description: Optional[str] = None
    decision_rules: Optional[list[dict]] = None
    exception_handlers: Optional[list[ExceptionHandler]] = None
    status: Optional[RuleStatus] = None
    expiry_date: Optional[str] = None
    priority: Optional[Literal["low", "medium", "high", "critical"]] = None


# 规则验证相关
class RuleValidationIssue(BaseModel):
    """规则验证问题"""
    issue_id: str
    issue_type: Literal["error", "warning"]
    code: str
    message: str
    affected_rule_id: Optional[str] = None
    suggestion: Optional[str] = None


class ImpactAnalysis(BaseModel):
    """规则变更影响分析"""
    rule_id: str
    rule_type: str
    affected_workflow_ids: list[str] = Field(default_factory=list)
    affected_workflow_count: int = 0
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    estimated_impact_percentage: float = 0.0
    recommendations: list[str] = Field(default_factory=list)
    change_history: list[dict] = Field(default_factory=list)
