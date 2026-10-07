// Shared session state/logic (PRD 5.2: desktop and mobile are two views of the *same*
// session state, not two separate implementations) -- both SessionPage (desktop) and
// MobileApp (Phase 2) drive the conversation through this one hook.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { sessionTab } from "../utils/sessionTabs";
import type {
  ManufacturingContext, RegenerateGraphCheck, WorkflowMetaUpdate, WorkflowRecord, WorkflowSummary,
} from "../api/types";

export function useWorkflowSession() {
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [active, setActive] = useState<WorkflowRecord | null>(null);
  const [sending, setSending] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState(false);

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

  // Initial load only -- opens the first in-progress session (not an archived/deleted one).
  useEffect(() => {
    refreshList()
      .then((list) => {
        const first = list.find((w) => sessionTab(w) === "active") ?? list.find((w) => sessionTab(w) !== "deleted");
        if (first) return selectWorkflow(first.id);
      })
      .catch((e) => setError(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  // Resolves to whether the turn went through. On failure the optimistic bubble is taken back
  // out and the caller puts the text back into the input box -- what the expert said is never
  // lost to a timeout (B1).
  const sendTurn = useCallback(
    async (text: string, rawTranscript?: string): Promise<boolean> => {
      if (!active) return false;
      const workflowId = active.id;
      const localId = `local-${Date.now()}`;
      setSending(true);
      setError(null);
      // Optimistic local append so the expert's own message shows immediately.
      setActive((prev) =>
        prev
          ? { ...prev, turns: [...prev.turns, { turn_id: localId, role: "expert", text, raw_transcript: rawTranscript ?? null }] }
          : prev,
      );
      try {
        await api.postTurn(workflowId, text, rawTranscript);
        const refreshed = await api.getWorkflow(workflowId);
        setActive(refreshed);
        await refreshList();
        return true;
      } catch (e) {
        setActive((prev) =>
          prev && prev.id === workflowId ? { ...prev, turns: prev.turns.filter((t) => t.turn_id !== localId) } : prev,
        );
        setError(`这一句没有发送成功，已放回输入框，可以直接重发。（${String(e)}）`);
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

  // 「继续修改」(section 17): a confirmed workflow that isn't in a dataset goes back into the
  // review conversation.
  const reopenWorkflow = useCallback(async () => {
    if (!active) return;
    setError(null);
    try {
      const record = await api.reopenWorkflow(active.id);
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

  // Manual drag on either DAG tab (section 18: SOP step graph or task graph). Optimistic +
  // local-only: unlike the other actions here, this never refetches the whole record -- a drag
  // is a view preference, not a conversation turn, so it must not clobber an in-flight
  // sendTurn's optimistic append or reset scroll position.
  const moveNode = useCallback(
    (nodeId: string, position: { x: number; y: number }, layer: "sop" | "task" = "sop") => {
      if (!active) return;
      setActive((prev) => {
        if (!prev) return prev;
        if (layer === "task") {
          if (!prev.task_workflow) return prev;
          return {
            ...prev,
            task_workflow: {
              ...prev.task_workflow,
              graph: {
                ...prev.task_workflow.graph,
                nodes: prev.task_workflow.graph.nodes.map((n) =>
                  n.node_id === nodeId ? { ...n, manual_position: position } : n,
                ),
              },
            },
          };
        }
        return {
          ...prev,
          graph: {
            ...prev.graph,
            nodes: prev.graph.nodes.map((n) => (n.node_id === nodeId ? { ...n, manual_position: position } : n)),
          },
        };
      });
      api.moveNode(active.id, nodeId, position, layer).catch((e) => setError(String(e)));
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
      const errorMsg = String(e);
      // Extract error type from API response for better UX
      const isTimeout = errorMsg.includes("超时") || errorMsg.includes("timeout");
      const errorType = isTimeout ? "timeout" : "other";
      setError(JSON.stringify({ message: errorMsg, type: errorType }));
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
    regenerating,
    selectWorkflow,
    createWorkflow,
    sendTurn,
    confirmWorkflow,
    reopenWorkflow,
    updateManufacturingContext,
    updateWorkflowMeta,
    moveNode,
    checkRegenerateGraph,
    regenerateGraph,
  };
}
