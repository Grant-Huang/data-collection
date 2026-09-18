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
