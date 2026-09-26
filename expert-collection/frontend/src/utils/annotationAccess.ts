// Who may act on a record right now -- the frontend mirror of the checks in
// backend routers/annotations.py::_role_for, run *before* the person does the work. The
// backend still enforces all of this; this only decides what the UI offers.
import type { AnnotationStage, PriorRecordSummary } from "../api/types";

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
