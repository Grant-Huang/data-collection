// Shared session state/logic (PRD 5.2: desktop and mobile are two views of the *same*
// session state, not two separate implementations) -- both SessionPage (desktop) and
// MobileApp (Phase 2) drive the conversation through this one hook.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { WorkflowRecord, WorkflowSummary } from "../api/types";

export function useWorkflowSession() {
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

  const createWorkflow = useCallback(async () => {
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
  }, [refreshList]);

  const sendTurn = useCallback(
    async (text: string) => {
      if (!active) return;
      setSending(true);
      setError(null);
      // Optimistic local append so the expert's own message shows immediately.
      setActive((prev) =>
        prev
          ? { ...prev, turns: [...prev.turns, { turn_id: `local-${Date.now()}`, role: "expert", text }] }
          : prev,
      );
      try {
        await api.postTurn(active.id, text);
        const refreshed = await api.getWorkflow(active.id);
        setActive(refreshed);
        await refreshList();
      } catch (e) {
        setError(String(e));
      } finally {
        setSending(false);
      }
    },
    [active, refreshList],
  );

  const confirmWorkflow = useCallback(async () => {
    if (!active) return;
    setError(null);
    try {
      const record = await api.confirmWorkflow(active.id);
      setActive(record);
      await refreshList();
    } catch (e) {
      setError(String(e));
    }
  }, [active, refreshList]);

  return {
    workflows,
    active,
    sending,
    creating,
    error,
    selectWorkflow,
    createWorkflow,
    sendTurn,
    confirmWorkflow,
  };
}
