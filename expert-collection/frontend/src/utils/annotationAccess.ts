// Who may act on a record right now -- the frontend mirror of the checks in
// backend routers/annotations.py, run *before* the person does the work (previously the
// "same person" error only came back after submitting). The backend still enforces all of
// this; this only decides what the UI offers.
import type { AnnotationStage, Graph, GraphNode, NodeVerdicts, PriorRecordSummary } from "../api/types";
import type { NodeDecoration } from "../components/DagView";

const norm = (s: string) => s.trim().toLowerCase();

export interface AccessInfo {
  canAct: boolean;
  reason: string | null; // why not, shown up front
  actionLabel: string; // button text in the list
}

export function accessFor(
  rec: Pick<PriorRecordSummary, "stage" | "round_annotator_names" | "round_reworker_name">,
  annotatorName: string,
): AccessInfo {
  const me = norm(annotatorName);
  const stage: AnnotationStage = rec.stage;
  if (stage === "done") return { canAct: false, reason: null, actionLabel: "查看" };
  if (stage === "rework") return { canAct: true, reason: null, actionLabel: "去返工" };
  const label = stage === "arbitration" ? "去仲裁" : stage === "second_review" ? "去复核" : "去标注";
  if (!me) return { canAct: true, reason: null, actionLabel: label };
  if (rec.round_reworker_name && norm(rec.round_reworker_name) === me) {
    return { canAct: false, reason: "你是本轮修正图的返工人，不能复核自己的返工", actionLabel: "查看" };
  }
  if (rec.round_annotator_names.some((n) => norm(n) === me)) {
    return {
      canAct: false,
      reason: stage === "arbitration" ? "你是本轮的独立标注人之一，不能担任仲裁人" : "你已经标注过本轮，第二次独立标注需要换一个人",
      actionLabel: "查看",
    };
  }
  return { canAct: true, reason: null, actionLabel: label };
}

// --- node verdict helpers (same semantics as backend app/rework.py) ---

export function predecessors(graph: Graph, nodeId: string): GraphNode[] {
  const ids: string[] = [];
  for (const e of graph.edges) if (e.to === nodeId && !ids.includes(e.from)) ids.push(e.from);
  return ids.map((id) => graph.nodes.find((n) => n.node_id === id)).filter((n): n is GraphNode => !!n);
}

export function parseVerdict(v: string | undefined): { kind: "keep" | "delete" | "merge_into"; target: string | null } {
  if (!v || v === "keep") return { kind: "keep", target: null };
  if (v.startsWith("merge_into:")) return { kind: "merge_into", target: v.slice("merge_into:".length) };
  return { kind: "delete", target: null };
}

export function describeVerdict(graph: Graph, v: string): string {
  const { kind, target } = parseVerdict(v);
  if (kind === "keep") return "保留";
  if (kind === "delete") return "删除";
  const t = graph.nodes.find((n) => n.node_id === target);
  return `合并进「${t?.label ?? target}」`;
}

export const DELETE_COLOR = "#dc2626";
export const MERGE_COLOR = "#7c3aed";

export function verdictDecorations(verdicts: NodeVerdicts, selectedId: string | null): Record<string, NodeDecoration> {
  const out: Record<string, NodeDecoration> = {};
  for (const [id, v] of Object.entries(verdicts)) {
    const { kind } = parseVerdict(v);
    if (kind === "delete") out[id] = { border: DELETE_COLOR, badge: "删除", badgeColor: DELETE_COLOR, faded: true };
    if (kind === "merge_into") out[id] = { border: MERGE_COLOR, badge: "合并", badgeColor: MERGE_COLOR };
  }
  if (selectedId) out[selectedId] = { ...(out[selectedId] ?? {}), selected: true };
  return out;
}
