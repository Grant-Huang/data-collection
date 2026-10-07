// PRD 5.x mobile nav (top-left icon opens history) reused as-is for the desktop left rail;
// desktop just always shows it docked instead of as a slide-over.
import type { WorkflowMetaUpdate, WorkflowSummary } from "../api/types";
import { WorkflowMenu } from "./WorkflowMenu";
import { SessionTabBar } from "./SessionTabBar";
import { EMPTY_TEXT, filterSessions, sessionTab, tabCounts, type SessionTab } from "../utils/sessionTabs";
import { useEffect, useMemo, useState } from "react";

const STATUS_LABEL: Record<string, string> = {
  draft: "草稿",
  collecting: "采集中",
  needs_confirmation: "待确认",
  expert_confirmed: "已确认",
};

interface Props {
  workflows: WorkflowSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  creating: boolean;
  onUpdateMeta: (id: string, patch: WorkflowMetaUpdate) => void;
  onExport?: (workflowId: string) => void;
}

export function HistoryDrawer({
  workflows, activeId, onSelect, onCreate, creating,
  onUpdateMeta, onExport,
}: Props) {
  const activeWorkflow = workflows.find((w) => w.id === activeId);
  const [tab, setTab] = useState<SessionTab>(activeWorkflow ? sessionTab(activeWorkflow) : "active");
  const [query, setQuery] = useState("");
  const counts = useMemo(() => tabCounts(workflows), [workflows]);
  const rows = useMemo(() => filterSessions(workflows, tab, query), [workflows, tab, query]);

  // The open session follows its own status: confirming it (or archiving it from the menu)
  // moves it to another tab, and the list should not leave it behind in the old one.
  const activeTab = activeWorkflow ? sessionTab(activeWorkflow) : null;
  useEffect(() => {
    if (activeTab) setTab(activeTab);
  }, [activeId, activeTab]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: 16, borderBottom: "1px solid #e5e7eb" }}>
        <button
          onClick={onCreate}
          disabled={creating}
          style={{
            width: "100%",
            border: "none",
            borderRadius: 8,
            padding: "10px 0",
            background: "#2a78d6",
            color: "#fff",
            fontWeight: 600,
            cursor: creating ? "default" : "pointer",
          }}
        >
          + 新建会话
        </button>
      </div>
      <SessionTabBar tab={tab} onTab={setTab} counts={counts} query={query} onQuery={setQuery} />
      <div role="tabpanel" style={{ flex: 1, overflowY: "auto" }}>
        {rows.map((w) => (
          <div
            key={w.id}
            data-session-row
            onClick={() => onSelect(w.id)}
            style={{
              padding: "12px 16px",
              cursor: "pointer",
              background: w.id === activeId ? "#eef4fc" : "transparent",
              borderLeft: w.id === activeId ? "3px solid #2a78d6" : "3px solid transparent",
              opacity: w.deleted ? 0.55 : 1,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              {w.pinned && <span title="已置顶" style={{ fontSize: 11 }}>📌</span>}
              <div style={{ flex: 1, minWidth: 0, fontSize: 13, fontWeight: 600, color: "#1f2937", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {w.name}
              </div>
              <WorkflowMenu
                workflow={w}
                onRename={(name) => onUpdateMeta(w.id, { name })}
                onTogglePin={() => onUpdateMeta(w.id, { pinned: !w.pinned })}
                onToggleArchive={() => onUpdateMeta(w.id, { archived: !w.archived })}
                onToggleDelete={() => onUpdateMeta(w.id, { deleted: !w.deleted })}
                onExport={onExport}
              />
            </div>
            <div style={{ fontSize: 11.5, color: "#667085", marginTop: 4, display: "flex", justifyContent: "space-between" }}>
              <span>{STATUS_LABEL[w.status] ?? w.status}{w.archived ? "・已归档" : ""}</span>
              <span>{Math.round(w.completion_score * 100)}%</span>
            </div>
          </div>
        ))}
        {rows.length === 0 && (
          <div style={{ padding: 16, fontSize: 12.5, color: "#667085" }}>
            {query.trim() ? "没有名称匹配的会话。" : workflows.length === 0 ? "还没有会话，点击上方开始第一个。" : EMPTY_TEXT[tab]}
          </div>
        )}
      </div>
    </div>
  );
}
