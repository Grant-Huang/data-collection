// Mirrors expert-collection/backend/app/models.py -- kept as a hand-written, minimal subset
// (Phase 1 scope only) rather than codegen, since the backend surface is still small and
// changing quickly.

export type NodeType =
  | "start" | "activity" | "decision" | "parallel_split" | "parallel_join"
  | "merge" | "approval" | "handoff" | "wait" | "end";

export type EdgeType =
  | "normal" | "conditional" | "parallel" | "merge" | "handoff" | "approval"
  | "timeout" | "exception_forward";

export type WorkflowStatus = "draft" | "collecting" | "needs_confirmation" | "expert_confirmed";

export interface RetrySemantics {
  enabled: boolean;
  rework_reference_node_id: string | null;
  condition: string | null;
  description: string | null;
}

export interface GraphNode {
  node_id: string;
  node_type: NodeType;
  label: string;
  actor_roles: string[];
  decision_question: string | null;
  confidence: number;
  expert_confirmed: boolean;
  source_turn_ids: string[];
  retry_semantics: RetrySemantics | null;
  manual_position: { x: number; y: number } | null;
}

export interface GraphEdge {
  edge_id: string;
  from: string;
  to: string;
  edge_type: EdgeType;
  condition: string | null;
  confidence: number;
  expert_confirmed: boolean;
  source_turn_ids: string[];
}

export interface Graph {
  graph_type: "dag";
  start_node_ids: string[];
  end_node_ids: string[];
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface ConversationTurn {
  turn_id: string;
  role: "expert" | "assistant";
  // Full plain text -- always present, and the only field older records have.
  text: string;
  // Assistant turns only (optional): the same message split into layers so the bubble can
  // render them separately -- restatement of what was recorded, the question, why it's
  // asked, and the chips offered with it (kept so the history shows what was picked).
  ack?: string | null;
  question?: string | null;
  why?: string | null;
  chips?: string[] | null;
  chip_mode?: "prefill" | "multi_select" | null;
}

export interface NextQuestion {
  target: string;
  priority: string;
  question: string;
  chips: string[] | null;
  // "prefill" (or omitted): clicking a chip fills the whole draft box, single choice --
  // this is also how the Scenario A-group's "简单说/详细说" mode chips work (the chip text
  // IS the answer template, the expert types after it -- no separate mode round trip).
  // "multi_select": chips toggle on/off, expert confirms the combined selection before it
  // goes into the draft box (Case Context B-group). Never auto-sends either way.
  chip_mode?: "prefill" | "multi_select" | null;
  ack?: string | null;
  why?: string | null;
}

export interface CaseContext {
  scenario_trigger: string | null;
  scenario_goal: string | null;
  scenario_success: string | null;
  known_info: string | null;
  unknown_info: string | null;
  constraints: string | null;
  available_resources: string | null;
  experience_notes?: string | null;
  detail_level: Record<string, string>;
  skipped_fields: string[];
}

export type ManufacturingMode =
  | "mass_repetitive" | "high_automation" | "high_mix_low_volume" | "eto_mto"
  | "large_project" | "regulated_traceable" | "other";

export const MANUFACTURING_MODE_LABELS: Record<ManufacturingMode, string> = {
  mass_repetitive: "大批量重复生产",
  high_automation: "高自动化产线",
  high_mix_low_volume: "多品种小批量",
  eto_mto: "按单设计/按单生产（ETO/MTO）",
  large_project: "大型项目制造",
  regulated_traceable: "强监管/可追溯行业",
  other: "其他",
};

export interface ManufacturingContext {
  manufacturing_mode: ManufacturingMode | null;
  industry: string | null;
  site_type: string | null;
  process_area: string | null;
  product_family: string | null;
  shift_context: string | null;
}

// §14.4 Dataset Slice -- must match backend dataset_records.SLICEABLE_FIELDS.
export const SLICEABLE_FIELDS: { field: keyof ManufacturingContext; label: string }[] = [
  { field: "manufacturing_mode", label: "制造模式" },
  { field: "industry", label: "行业" },
  { field: "site_type", label: "现场类型" },
  { field: "process_area", label: "工艺/工序范围" },
  { field: "product_family", label: "产品族" },
];

export interface ValidationIssue {
  level: "error" | "warning";
  code: string;
  message: string;
  node_id: string | null;
  edge_id: string | null;
}

export interface Completion {
  score: number;
  ready_for_confirmation: boolean;
}

export interface WorkflowSummary {
  id: string;
  name: string;
  status: WorkflowStatus;
  completion_score: number;
  updated_at: string;
}

export interface WorkflowRecord {
  id: string;
  name: string;
  status: WorkflowStatus;
  stage: string;
  graph: Graph;
  turns: ConversationTurn[];
  unresolved: NextQuestion[];
  completion: Completion;
  validation: ValidationIssue[];
  case_context: CaseContext | null;
  manufacturing_context: ManufacturingContext | null;
  created_at: string;
  updated_at: string;
}

export interface TurnResponse {
  assistant_reply: string;
  graph_ops_applied: number;
  current_dag: Graph;
  completion: Completion;
  validation: ValidationIssue[];
  next_question: NextQuestion | null;
}

// --- Dataset / Dashboard (PRD 12/13) ---

export type SourceType = "expert_collected" | "public_extracted";
export type ScoreBand = "good" | "warning" | "poor" | "insufficient_sample";

export interface DimensionScore {
  score: number | null;
  band: ScoreBand;
  sub_indicators: Record<string, unknown>;
  scope_note: string;
  explanation: string;
}

export const DIMENSION_ORDER = [
  "coverage", "balance", "completeness", "graph_completeness", "extractability",
  "authenticity", "annotation_readiness", "diversity", "structural_diversity", "low_leakage_risk",
] as const;

export const DIMENSION_LABELS: Record<string, string> = {
  coverage: "覆盖度", balance: "平衡度", completeness: "流程完整度",
  graph_completeness: "Graph 结构完整度", extractability: "可抽取性",
  authenticity: "真实性与来源可信度", annotation_readiness: "标注成熟度",
  diversity: "多样性", structural_diversity: "结构多样性", low_leakage_risk: "低泄漏风险",
};

// Mirrors app/quality.py DIMENSION_WEIGHTS -- display-only (the backend is the source of
// truth for the actual weighted overall score).
export const DIMENSION_WEIGHTS: Record<string, number> = {
  coverage: 0.15, balance: 0.10, completeness: 0.15, graph_completeness: 0.15,
  extractability: 0.10, authenticity: 0.10, annotation_readiness: 0.10,
  diversity: 0.05, structural_diversity: 0.05, low_leakage_risk: 0.05,
};

export interface DatasetReadiness {
  overall: number | null;
  band: ScoreBand;
  sample_size: number;
  dimensions: Record<string, DimensionScore>;
}

export interface DatasetVersionSummary {
  id: string;
  source_type: SourceType;
  version_number: number;
  workflow_count: number;
  total_steps: number;
  microflow_count: number | null;
  created_at: string;
  readiness: DatasetReadiness;
  archived: boolean;
  is_gold: boolean;
}

// --- Prior + Gold annotation (IMPLEMENTATION_PLAN.md section 9.2, section 9 §9 Phase C-2) ---
// "Public/LLM-derived Prior" -> "Expert-annotated Prior": any single annotation flips this
// (unchanged since Phase 7). Gold is a stricter status layered on top, requiring two
// independent annotations that agree, or a third person's arbitration when they don't --
// see gold_status. Applies to both public_extracted and expert_collected now.

export type PriorStatus = "raw" | "expert_annotated";
export type PriorVerdict = "accepted" | "needs_revision" | "rejected";
export type GoldStatus = "not_gold" | "pending_second_review" | "disputed_pending_arbitration" | "gold";
export type AnnotationRole = "independent" | "arbitration";
// node_id -> "keep" | "delete" | "merge_into:<other_node_id>"
export type NodeVerdicts = Record<string, string>;

export interface PriorAnnotation {
  annotation_id: string;
  version_id: string;
  record_id: string;
  based_on_annotation_id: string | null;
  verdict: PriorVerdict;
  node_verdicts: NodeVerdicts;
  note: string | null;
  actor_role: string | null;
  annotator_name: string;
  role_in_process: AnnotationRole;
  annotated_at: string;
}

export interface PriorRecordDetail {
  record_id: string;
  name: string;
  graph: Graph;
  prior_status: PriorStatus;
  gold_status: GoldStatus;
  annotations: PriorAnnotation[]; // oldest first
}

export interface PriorRecordSummary {
  record_id: string;
  name: string;
  node_count: number;
  prior_status: PriorStatus;
  latest_verdict: PriorVerdict | null;
  gold_status: GoldStatus;
}

export interface AnnotationSummary {
  version_id: string;
  total_records: number;
  annotated_records: number;
  verdict_counts: Partial<Record<PriorVerdict, number>>;
  gold_counts: Partial<Record<GoldStatus, number>>;
  agreement_kappa: number | null;
}

export const GOLD_STATUS_LABELS: Record<GoldStatus, string> = {
  not_gold: "非 Gold",
  pending_second_review: "待第二人复核",
  disputed_pending_arbitration: "分歧待仲裁",
  gold: "★ Gold",
};

export const VERDICT_LABELS: Record<PriorVerdict, string> = {
  accepted: "采纳", needs_revision: "需要修改", rejected: "丢弃",
};

// --- Experiment Center (PRD 14) ---

export type ExperimentMethod = "consensus_dfg" | "pm4py_inductive" | "pm4py_heuristics" | "llm_extractor";
export type ExperimentStatus = "queued" | "running" | "completed" | "failed";
export type Representation = "sequence_projection" | "node_edge_graph" | "event_log" | "text_serialization";
export type InputVersion = "raw" | "anonymized" | "role_normalized";

export const METHOD_LABELS: Record<ExperimentMethod, string> = {
  consensus_dfg: "consensus_dfg（规则 baseline）",
  pm4py_inductive: "pm4py_inductive（Inductive Miner）",
  pm4py_heuristics: "pm4py_heuristics（Heuristics Miner）",
  llm_extractor: "基于 LLM 的抽取器",
};

export const IMPLEMENTED_METHODS: ExperimentMethod[] = ["consensus_dfg", "pm4py_inductive", "pm4py_heuristics"];

export interface CreateExperimentRequest {
  name: string;
  source_type: SourceType;
  dataset_version_id: string;
  input_version: InputVersion;
  representation: Representation;
  method: ExperimentMethod;
  model_name?: string | null;
  prompt_version?: string | null;
  temperature?: number | null;
  seed: number;
  train_split: number;
  gold_nodes: boolean;
  gold_edges: boolean;
  gold_boundary: boolean;
  gold_roles: boolean;
  actor_role?: string | null;
}

export interface ExperimentSummary {
  id: string;
  name: string;
  dataset_version_id: string;
  dataset_label: string;
  method: ExperimentMethod;
  model_name: string | null;
  status: ExperimentStatus;
  created_by: string;
  created_at: string;
  node_f1: number | null;
  graph_structural_f1: number | null;
}

export interface ErrorCase {
  workflow_name: string;
  node_f1: number;
  edge_f1: number;
  structural_match: number;
  group: string;
}

export interface ErrorCluster {
  label: string;
  description: string;
  workflow_names: string[];
}

export interface ExperimentDetail extends ExperimentSummary {
  source_type: SourceType;
  input_version: InputVersion;
  representation: Representation;
  prompt_version: string | null;
  temperature: number | null;
  seed: number;
  train_split: number;
  train_count: number | null;
  test_count: number | null;
  metrics: Record<string, number>;
  explanation: string | null;
  explanation_edited: boolean;
  consensus_graph: Graph | null;
  error_analysis: ErrorCase[];
  error_clusters: ErrorCluster[];
  failure_reason: string | null;
}

export interface ComparisonMetricRow {
  key: string;
  label: string;
  direction: "higher" | "lower";
  values: (number | null)[];
  best_value: number | null;
}

export interface ComparisonResult {
  experiments: ExperimentSummary[];
  metric_table: { rows: ComparisonMetricRow[] };
  narrative: string;
}

// --- Settings (PRD 17) ---

// Level-first model config (IMPLEMENTATION_PLAN.md section 11): each level (L/C_standard/
// C_flagship) carries the connection details exactly once; a slot only references which
// level it uses plus what's genuinely per-task (enabled, temperature) -- no more retyping
// the same endpoint/model/key into every slot that happens to use the same connection.
export interface LlmLevelConfig {
  endpoint?: string;
  model_name?: string;
  api_key_set: boolean;
}

export interface LlmSlotConfig {
  level: string;
  enabled?: boolean;
  temperature?: number;
}

export interface Settings {
  llm_levels: Record<string, LlmLevelConfig>;
  llm_slots: Record<string, LlmSlotConfig>;
  voice: { workspace_id: string; realtime_model: string };
  quality_params: {
    min_sample_size: number;
    near_dup_text_threshold: number;
    near_dup_structure_threshold: number | null;
    completion_threshold: number;
    publish_prompt_count: number;
    publish_prompt_days: number;
  };
  run_params: {
    max_concurrent_experiments: number;
    run_timeout_seconds: number;
    audit_log_retention_days: number;
    mobile_session_timeout_minutes: number | null;
  };
}

export const LLM_SLOT_LABELS: Record<string, string> = {
  guide_service: "专家采集会话引导", mobile_speech_polish: "移动端语音口述整理",
  experiment_explain: "实验结果文字解读", experiment_compare_explain: "多实验对比解读",
  error_clustering: "Error Analysis 案例聚类归纳", anonymize_name: "导出匿名化人名脱敏",
  role_normalize: "角色归一化", dashboard_explain: "Dashboard 评分项解释生成",
};

export const LLM_LEVEL_LABELS: Record<string, string> = {
  L: "L（本地 7B）", C_standard: "C-标准档", C_flagship: "C-旗舰档",
};

// --- Admin (PRD 16) ---

export type Role = "expert" | "researcher" | "admin";

export const ROLE_LABELS: Record<Role, string> = { expert: "专家", researcher: "研究员", admin: "管理员" };

export interface AuditLogEntry {
  id: string;
  actor_role: string;
  action: string;
  detail: Record<string, unknown>;
  created_at: string;
}
