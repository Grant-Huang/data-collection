// PRD 4.2/5.1: history drawer is an overlay, not a separate route -- tapping a workflow or
// the backdrop closes it and returns to the session page.
import type { WorkflowSummary } from "../api/types";

const STATUS_LABEL: Record<string, string> = {
  draft: "草稿", collecting: "采集中", needs_confirmation: "待确认", expert_confirmed: "已确认",
};

interface Props {
  open: boolean;
  workflows: WorkflowSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onClose: () => void;
  creating: boolean;
}

export function HistorySheet({ open, workflows, activeId, onSelect, onCreate, onClose, creating }: Props) {
  return (
    <>
      <div
        onClick={onClose}
        style={{
          position: "fixed", inset: 0, background: "rgba(15,23,42,0.35)", zIndex: 30,
          opacity: open ? 1 : 0, pointerEvents: open ? "auto" : "none", transition: "opacity 0.2s",
        }}
      />
      <div
        style={{
          position: "fixed", top: 0, bottom: 0, left: 0, width: "82%", maxWidth: 320,
          background: "#fff", zIndex: 31, boxShadow: "4px 0 24px rgba(0,0,0,0.15)",
          transform: open ? "translateX(0)" : "translateX(-100%)", transition: "transform 0.22s ease-out",
          display: "flex", flexDirection: "column",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 16px", borderBottom: "1px solid #e5e7eb" }}>
          <div style={{ fontWeight: 700, fontSize: 14 }}>我的流程</div>
          <button aria-label="关闭" onClick={onClose} style={{ border: "none", background: "none", fontSize: 18, minWidth: 44, minHeight: 44 }}>
            ✕
          </button>
        </div>
        <div style={{ padding: 16 }}>
          <button
            onClick={() => {
              onCreate();
              onClose();
            }}
            disabled={creating}
            style={{ width: "100%", border: "none", borderRadius: 8, padding: "12px 0", background: "#2a78d6", color: "#fff", fontWeight: 600, minHeight: 44 }}
          >
            + 新建一个流程
          </button>
        </div>
        <div style={{ flex: 1, overflowY: "auto" }}>
          {workflows.map((w) => (
            <div
              key={w.id}
              onClick={() => {
                onSelect(w.id);
                onClose();
              }}
              style={{
                padding: "14px 16px", minHeight: 44,
                background: w.id === activeId ? "#eef4fc" : "transparent",
                borderLeft: w.id === activeId ? "3px solid #2a78d6" : "3px solid transparent",
              }}
            >
              <div style={{ fontSize: 13.5, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{w.name}</div>
              <div style={{ fontSize: 11.5, color: "#667085", marginTop: 4, display: "flex", justifyContent: "space-between" }}>
                <span>{STATUS_LABEL[w.status] ?? w.status}</span>
                <span>{Math.round(w.completion_score * 100)}%</span>
              </div>
            </div>
          ))}
          {workflows.length === 0 && <div style={{ padding: 16, fontSize: 12.5, color: "#667085" }}>还没有流程，点击上方开始第一个。</div>}
        </div>
      </div>
    </>
  );
}
