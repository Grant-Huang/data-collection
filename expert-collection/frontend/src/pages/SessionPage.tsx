// Desktop three-column layout (PRD 4/5: session history | conversation | DAG) for the
// expert conversational collection loop. The left (history) and right (DAG) panels are
// resizable and collapsible; the middle conversation column always fills what's left.
import { useState } from "react";
import { useWorkflowSession } from "../hooks/useWorkflowSession";
import { useResizablePanel } from "../hooks/useResizablePanel";
import { ChatPanel } from "../components/ChatPanel";
import { DagView } from "../components/DagView";
import { HistoryDrawer } from "../components/HistoryDrawer";
import { ResizeHandle } from "../components/ResizeHandle";
import { MANUFACTURING_MODE_LABELS, type ManufacturingMode } from "../api/types";

export function SessionPage() {
  const {
    workflows, active, sending, creating, error,
    selectWorkflow, createWorkflow, sendTurn, confirmWorkflow, updateManufacturingContext,
  } = useWorkflowSession();

  // Defaults are 18%/30% of the viewport width (the rest goes to the conversation column);
  // only used the first time, before anything is stored -- after that the saved px width wins.
  // Node ids to highlight on the DAG while the expert hovers a message's "图上 +N" tag.
  const [highlightNodeIds, setHighlightNodeIds] = useState<string[] | null>(null);

  const viewportWidth = typeof window !== "undefined" ? window.innerWidth : 1440;
  const left = useResizablePanel("history", Math.round(viewportWidth * 0.18), 160, 560);
  const right = useResizablePanel("dag", Math.round(viewportWidth * 0.3), 220, 900);

  return (
    <div style={{ display: "flex", height: "100%", position: "relative", fontFamily: "-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif" }}>
      <div style={{ width: left.collapsed ? 0 : left.width, overflow: "hidden", flexShrink: 0, transition: left.collapsed ? "width 0.15s ease-out" : undefined }}>
        <div style={{ width: left.width, height: "100%" }}>
          <HistoryDrawer
            workflows={workflows}
            activeId={active?.id ?? null}
            onSelect={selectWorkflow}
            onCreate={createWorkflow}
            creating={creating}
          />
        </div>
      </div>
      <ResizeHandle
        panelSide="left"
        collapsed={left.collapsed}
        onToggleCollapse={left.toggleCollapsed}
        onResize={(dx) => left.resizeBy(dx, 1)}
      />

      <div style={{ flex: 1, minWidth: 0, borderLeft: "1px solid #e5e7eb", borderRight: "1px solid #e5e7eb", display: "flex", flexDirection: "column" }}>
        {active ? (
          <>
            <div style={{ padding: "12px 16px", borderBottom: "1px solid #e5e7eb" }}>
              <div style={{ fontWeight: 700, fontSize: 14 }}>{active.name}</div>
              <div style={{ fontSize: 11.5, color: "#667085", marginTop: 2 }}>
                完成度 {Math.round(active.completion.score * 100)}%
                {active.completion.ready_for_confirmation && active.status !== "expert_confirmed" && "・可以确认提交了"}
                {active.status === "expert_confirmed" && "・已确认"}
              </div>
              {/* §14.4 Dataset Slice -- a static classification tag, editable any time, not
                  part of the FSM conversation (it's not scenario narrative). */}
              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <select
                  key={`mode-${active.id}`}
                  defaultValue={active.manufacturing_context?.manufacturing_mode ?? ""}
                  onChange={(e) =>
                    updateManufacturingContext({
                      manufacturing_mode: (e.target.value || null) as ManufacturingMode | null,
                    })
                  }
                  style={{ fontSize: 11.5, border: "1px solid #d0d5dd", borderRadius: 6, padding: "3px 6px", color: "#475569" }}
                >
                  <option value="">制造模式（未填写）</option>
                  {Object.entries(MANUFACTURING_MODE_LABELS).map(([v, label]) => (
                    <option key={v} value={v}>{label}</option>
                  ))}
                </select>
                <input
                  key={`industry-${active.id}`}
                  defaultValue={active.manufacturing_context?.industry ?? ""}
                  placeholder="行业（可选，如：汽车制造）"
                  onBlur={(e) => updateManufacturingContext({ industry: e.target.value || null })}
                  style={{ fontSize: 11.5, border: "1px solid #d0d5dd", borderRadius: 6, padding: "3px 6px", color: "#475569", width: 160 }}
                />
              </div>
            </div>
            <div style={{ flex: 1, minHeight: 0 }}>
              <ChatPanel
                turns={active.turns}
                graph={active.graph}
                onHighlightNodes={setHighlightNodeIds}
                nextQuestion={active.unresolved[0] ?? null}
                onSend={sendTurn}
                sending={sending}
                confirmed={active.status === "expert_confirmed"}
              />
            </div>
            {active.completion.ready_for_confirmation && active.status !== "expert_confirmed" && (
              <div style={{ padding: 16, borderTop: "1px solid #e5e7eb" }}>
                <button
                  onClick={confirmWorkflow}
                  style={{ width: "100%", border: "none", borderRadius: 8, padding: "10px 0", background: "#0ca30c", color: "#fff", fontWeight: 600, cursor: "pointer" }}
                >
                  确认并提交
                </button>
              </div>
            )}
          </>
        ) : (
          <div style={{ padding: 16, color: "#667085", fontSize: 13 }}>新建一个会话开始采集</div>
        )}
      </div>

      <ResizeHandle
        panelSide="right"
        collapsed={right.collapsed}
        onToggleCollapse={right.toggleCollapsed}
        onResize={(dx) => right.resizeBy(dx, -1)}
      />
      <div style={{ width: right.collapsed ? 0 : right.width, overflow: "hidden", flexShrink: 0, transition: right.collapsed ? "width 0.15s ease-out" : undefined }}>
        <div style={{ width: right.width, height: "100%" }}>
          {active && active.graph.nodes.length === 0 ? (
            // Scenario/Case Context questions (IMPLEMENTATION_PLAN.md section 9.1) come
            // before any graph node exists -- show that this is expected, not a stuck app.
            <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "#94a3b8", fontSize: 12.5, textAlign: "center", padding: 24 }}>
              背景信息收集中，还没开始画图……
            </div>
          ) : (
            active && <DagView graph={active.graph} highlightNodeIds={highlightNodeIds} />
          )}
        </div>
      </div>

      {error && (
        <div style={{ position: "absolute", bottom: 16, left: "50%", transform: "translateX(-50%)", background: "#fef2f2", border: "1px solid #fecaca", color: "#991b1b", borderRadius: 8, padding: "8px 12px", fontSize: 12, zIndex: 10 }}>
          {error}
        </div>
      )}
    </div>
  );
}
