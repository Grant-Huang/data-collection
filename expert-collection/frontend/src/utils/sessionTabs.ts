// Session-list tabs (left rail on desktop, history sheet on mobile). One session is in exactly
// one tab:
//   deleted   -> 已删除   (soft delete, restorable)
//   archived or confirmed -> 已完成 (archive = "I'm done with this one")
//   needs_confirmation    -> 待确认 (AI finished the draft; waiting for the expert's final yes)
//   anything else         -> 进行中 (the default)
import type { WorkflowSummary } from "../api/types";

export type SessionTab = "active" | "pending" | "done" | "deleted";

export const SESSION_TABS: { key: SessionTab; label: string }[] = [
  { key: "active", label: "进行中" },
  { key: "pending", label: "待确认" },
  { key: "done", label: "已完成" },
  { key: "deleted", label: "已删除" },
];

export function sessionTab(w: Pick<WorkflowSummary, "status" | "archived" | "deleted">): SessionTab {
  if (w.deleted) return "deleted";
  if (w.archived || w.status === "expert_confirmed") return "done";
  if (w.status === "needs_confirmation") return "pending";
  return "active";
}

export function tabCounts(workflows: WorkflowSummary[]): Record<SessionTab, number> {
  const counts: Record<SessionTab, number> = { active: 0, pending: 0, done: 0, deleted: 0 };
  for (const w of workflows) counts[sessionTab(w)] += 1;
  return counts;
}

/** Sessions in `tab` whose name contains `query` (case-insensitive, whitespace-trimmed). */
export function filterSessions(workflows: WorkflowSummary[], tab: SessionTab, query: string): WorkflowSummary[] {
  const q = query.trim().toLowerCase();
  return workflows.filter((w) => sessionTab(w) === tab && (!q || w.name.toLowerCase().includes(q)));
}

export const EMPTY_TEXT: Record<SessionTab, string> = {
  active: "没有进行中的会话，点上方「新建会话」开始。",
  pending: "没有待确认的会话。",
  done: "还没有已完成的会话。确认提交或归档后会出现在这里。",
  deleted: "没有已删除的会话。删除的会话可以在这里恢复。",
};

/** Which tab a session lands in after `patch` -- used to follow the session to its new tab. */
export function tabAfter(w: WorkflowSummary, patch: Partial<Pick<WorkflowSummary, "archived" | "deleted">>): SessionTab {
  return sessionTab({ ...w, ...patch });
}
