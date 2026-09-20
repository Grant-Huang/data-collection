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
    text: str


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


class PublishDatasetRequest(BaseModel):
    source_type: SourceType = "expert_collected"
    name: Optional[str] = None
    actor_role: Optional[str] = None


class ImportConfirmRequest(BaseModel):
    payload: dict
    name: Optional[str] = None
    actor_role: Optional[str] = None
    import_records_without_errors: bool = False


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
    failure_reason: Optional[str] = None


class ExplanationUpdateRequest(BaseModel):
    text: str


class ComparisonRequest(BaseModel):
    experiment_ids: list[str]


class ComparisonResult(BaseModel):
    experiments: list[ExperimentSummary]
    metric_table: dict
    narrative: str
