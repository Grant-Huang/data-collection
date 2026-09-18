// Desktop three-column layout (PRD 4/5: session history | conversation | DAG) for the
// expert conversational collection loop -- Phase 1 scope only.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { WorkflowRecord, WorkflowSummary } from "../api/types";
import { ChatPanel } from "../components/ChatPanel";
import { DagView } from "../components/DagView";
import { HistoryDrawer } from "../components/HistoryDrawer";

export function SessionPage() {
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [active, setActive] = useState<WorkflowRecord | null>(null);
  const [sending, setSending] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshList = useCallback(async () => {
    const list = await api.listWorkflows();
    setWorkflows(list);
    return list;
  }, []);

  const selectWorkflow = useCallback(async (id: string) => {
    setError(null);
    const record = await api.getWorkflow(id);
    setActive(record);
  }, []);

  useEffect(() => {
    refreshList()
      .then((list) => {
        if (list.length > 0) return selectWorkflow(list[0].id);
      })
      .catch((e) => setError(String(e)));
  }, [refreshList, selectWorkflow]);

  async function handleCreate() {
    setCreating(true);
    setError(null);
    try {
      const record = await api.createWorkflow();
      setActive(record);
      await refreshList();
    } catch (e) {
      setError(String(e));
    } finally {
      setCreating(false);
    }
  }

  async function handleSend(text: string) {
    if (!active) return;
    setSending(true);
    setError(null);
    // Optimistic local append so the expert's own message shows immediately.
    setActive({
      ...active,
      turns: [...active.turns, { turn_id: `local-${Date.now()}`, role: "expert", text }],
    });
    try {
      const resp = await api.postTurn(active.id, text);
      const refreshed = await api.getWorkflow(active.id);
      setActive(refreshed);
      void resp;
      await refreshList();
    } catch (e) {
      setError(String(e));
    } finally {
      setSending(false);
    }
  }

  async function handleConfirm() {
    if (!active) return;
    setError(null);
    try {
      const record = await api.confirmWorkflow(active.id);
      setActive(record);
      await refreshList();
    } catch (e) {
      setError(String(e));
    }
  }

  const errorIssues = active
    ? [] // live validation issues are shown inline via the last turn response; kept minimal for Phase 1
    : [];
  void errorIssues;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "240px 420px 1fr", height: "100vh", fontFamily: "-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif" }}>
      <div style={{ borderRight: "1px solid #e5e7eb" }}>
        <HistoryDrawer
          workflows={workflows}
          activeId={active?.id ?? null}
          onSelect={selectWorkflow}
          onCreate={handleCreate}
          creating={creating}
        />
      </div>

      <div style={{ borderRight: "1px solid #e5e7eb", display: "flex", flexDirection: "column" }}>
        {active ? (
          <>
            <div style={{ padding: "12px 16px", borderBottom: "1px solid #e5e7eb" }}>
              <div style={{ fontWeight: 700, fontSize: 14 }}>{active.name}</div>
              <div style={{ fontSize: 11.5, color: "#667085", marginTop: 2 }}>
                完成度 {Math.round(active.completion.score * 100)}%
                {active.completion.ready_for_confirmation && active.status !== "expert_confirmed" && "・可以确认提交了"}
                {active.status === "expert_confirmed" && "・已确认"}
              </div>
            </div>
            <div style={{ flex: 1, minHeight: 0 }}>
              <ChatPanel
                turns={active.turns}
                nextQuestion={active.unresolved[0] ?? null}
                onSend={handleSend}
                sending={sending}
                confirmed={active.status === "expert_confirmed"}
              />
            </div>
            {active.completion.ready_for_confirmation && active.status !== "expert_confirmed" && (
              <div style={{ padding: 16, borderTop: "1px solid #e5e7eb" }}>
                <button
                  onClick={handleConfirm}
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

      <div style={{ position: "relative" }}>
        {active && <DagView graph={active.graph} />}
        {error && (
          <div style={{ position: "absolute", bottom: 16, left: 16, right: 16, background: "#fef2f2", border: "1px solid #fecaca", color: "#991b1b", borderRadius: 8, padding: "8px 12px", fontSize: 12 }}>
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
