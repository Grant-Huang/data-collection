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
  text: string;
}

export interface NextQuestion {
  target: string;
  priority: string;
  question: string;
  chips: string[] | null;
}

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
}
