// PRD 5.x mobile nav (top-left icon opens history) reused as-is for the desktop left rail;
// desktop just always shows it docked instead of as a slide-over.
import type { WorkflowSummary } from "../api/types";

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
}

export function HistoryDrawer({ workflows, activeId, onSelect, onCreate, creating }: Props) {
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
      <div style={{ flex: 1, overflowY: "auto" }}>
        {workflows.map((w) => (
          <div
            key={w.id}
            onClick={() => onSelect(w.id)}
            style={{
              padding: "12px 16px",
              cursor: "pointer",
              background: w.id === activeId ? "#eef4fc" : "transparent",
              borderLeft: w.id === activeId ? "3px solid #2a78d6" : "3px solid transparent",
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 600, color: "#1f2937", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {w.name}
            </div>
            <div style={{ fontSize: 11.5, color: "#667085", marginTop: 4, display: "flex", justifyContent: "space-between" }}>
              <span>{STATUS_LABEL[w.status] ?? w.status}</span>
              <span>{Math.round(w.completion_score * 100)}%</span>
            </div>
          </div>
        ))}
        {workflows.length === 0 && (
          <div style={{ padding: 16, fontSize: 12.5, color: "#667085" }}>还没有会话，点击上方开始第一个。</div>
        )}
      </div>
    </div>
  );
}
