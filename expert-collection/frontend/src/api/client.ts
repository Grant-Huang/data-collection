import type { TurnResponse, WorkflowRecord, WorkflowSummary } from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${method} ${path} -> ${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listWorkflows: () => req<WorkflowSummary[]>("GET", "/api/expert-workflows"),
  createWorkflow: (name?: string) =>
    req<WorkflowRecord>("POST", "/api/expert-workflows", { name: name ?? null }),
  getWorkflow: (id: string) => req<WorkflowRecord>("GET", `/api/expert-workflows/${id}`),
  postTurn: (id: string, text: string) =>
    req<TurnResponse>("POST", `/api/expert-workflows/${id}/turns`, { text }),
  confirmWorkflow: (id: string) =>
    req<WorkflowRecord>("POST", `/api/expert-workflows/${id}/confirm`),
};
