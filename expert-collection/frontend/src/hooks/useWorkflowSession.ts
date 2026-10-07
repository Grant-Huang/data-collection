// Shared session state/logic (PRD 5.2: desktop and mobile are two views of the *same*
// session state, not two separate implementations) -- both SessionPage (desktop) and
// MobileApp (Phase 2) drive the conversation through this one hook.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { ManufacturingContext, WorkflowRecord, WorkflowSummary } from "../api/types";

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

  // Returns whether the turn went through. On failure the optimistic bubble is removed again
  // and the caller puts the text back into the input box (B1: never lose what the expert typed).
  const sendTurn = useCallback(
    async (text: string): Promise<boolean> => {
      if (!active) return false;
      const workflowId = active.id;
      const localId = `local-${Date.now()}`;
      setSending(true);
      setError(null);
      // Optimistic local append so the expert's own message shows immediately.
      setActive((prev) =>
        prev ? { ...prev, turns: [...prev.turns, { turn_id: localId, role: "expert", text }] } : prev,
      );
      try {
        await api.postTurn(workflowId, text);
        const refreshed = await api.getWorkflow(workflowId);
        setActive(refreshed);
        await refreshList();
        return true;
      } catch (e) {
        setActive((prev) =>
          prev && prev.id === workflowId ? { ...prev, turns: prev.turns.filter((t) => t.turn_id !== localId) } : prev,
        );
        setError(`这一轮没有发送成功，你的回答已放回输入框，可以直接重发。（${String(e)}）`);
        return false;
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

  // B5: persist a dragged node's position. Patched into local state directly (not replaced
  // by the server's copy) so a turn that is in flight at the same time can't be clobbered.
  const moveNode = useCallback(
    async (nodeId: string, position: { x: number; y: number }) => {
      if (!active) return;
      const workflowId = active.id;
      setActive((prev) =>
        prev && prev.id === workflowId
          ? {
              ...prev,
              graph: {
                ...prev.graph,
                nodes: prev.graph.nodes.map((n) => (n.node_id === nodeId ? { ...n, manual_position: position } : n)),
              },
            }
          : prev,
      );
      try {
        await api.updateNodePosition(workflowId, nodeId, position);
      } catch (e) {
        setError(String(e));
      }
    },
    [active],
  );

  const updateManufacturingContext = useCallback(
    async (patch: Partial<ManufacturingContext>) => {
      if (!active) return;
      setError(null);
      try {
        const record = await api.updateManufacturingContext(active.id, patch);
        setActive(record);
      } catch (e) {
        setError(String(e));
      }
    },
    [active],
  );

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
    updateManufacturingContext,
    moveNode,
  };
}
