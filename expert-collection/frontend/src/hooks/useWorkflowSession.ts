// Shared session state/logic (PRD 5.2: desktop and mobile are two views of the *same*
// session state, not two separate implementations) -- both SessionPage (desktop) and
// MobileApp (Phase 2) drive the conversation through this one hook.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type {
  ManufacturingContext, RegenerateGraphCheck, WorkflowMetaUpdate, WorkflowRecord, WorkflowSummary,
} from "../api/types";

export function useWorkflowSession() {
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [active, setActive] = useState<WorkflowRecord | null>(null);
  const [sending, setSending] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 左栏「显示已归档」切换 -- 默认关闭，归档就是要把会话从常规清单里挪走。
  const [showArchived, setShowArchived] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  const refreshList = useCallback(async (includeArchived = showArchived) => {
    const list = await api.listWorkflows(includeArchived);
    setWorkflows(list);
    return list;
  }, [showArchived]);

  const selectWorkflow = useCallback(async (id: string) => {
    setError(null);
    const record = await api.getWorkflow(id);
    setActive(record);
  }, []);

  // Initial load only -- picks the first workflow once. Toggling "显示已归档" below re-runs
  // refreshList on its own, but must NOT re-trigger this auto-select, or flipping the toggle
  // while mid-conversation would yank the expert back to workflow #1.
  useEffect(() => {
    refreshList(false)
      .then((list) => {
        if (list.length > 0) return selectWorkflow(list[0].id);
      })
      .catch((e) => setError(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleShowArchived = useCallback(() => {
    setShowArchived((prev) => {
      const next = !prev;
      api.listWorkflows(next).then(setWorkflows).catch((e) => setError(String(e)));
      return next;
    });
  }, []);

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

  // 左栏「...」下拉菜单：重命名 / 置顶 / 归档-取消归档。`workflowId` defaults to the active
  // workflow but takes an explicit id too, since the menu can act on a row that isn't
  // currently selected.
  const updateWorkflowMeta = useCallback(
    async (workflowId: string, patch: WorkflowMetaUpdate) => {
      setError(null);
      try {
        const record = await api.updateWorkflowMeta(workflowId, patch);
        if (active?.id === workflowId) setActive(record);
        await refreshList();
      } catch (e) {
        setError(String(e));
      }
    },
    [active, refreshList],
  );

  // 「用大模型根据会话内容重新生成流程图」-- always re-checks the server-side gate right
  // before calling, rather than trusting a check the caller ran earlier (the workflow could
  // have been published into a dataset in between).
  const checkRegenerateGraph = useCallback(async (): Promise<RegenerateGraphCheck | null> => {
    if (!active) return null;
    setError(null);
    try {
      return await api.regenerateGraphCheck(active.id);
    } catch (e) {
      setError(String(e));
      return null;
    }
  }, [active]);

  const regenerateGraph = useCallback(async () => {
    if (!active) return;
    setRegenerating(true);
    setError(null);
    try {
      const record = await api.regenerateGraph(active.id);
      setActive(record);
      await refreshList();
    } catch (e) {
      setError(String(e));
    } finally {
      setRegenerating(false);
    }
  }, [active, refreshList]);

  return {
    workflows,
    active,
    sending,
    creating,
    error,
    showArchived,
    toggleShowArchived,
    regenerating,
    selectWorkflow,
    createWorkflow,
    sendTurn,
    confirmWorkflow,
    updateManufacturingContext,
    updateWorkflowMeta,
    checkRegenerateGraph,
    regenerateGraph,
  };
}
