import type {
  AnnotationSummary,
  AuditLogEntry,
  ComparisonResult,
  CreateExperimentRequest,
  DatasetVersionSummary,
  ExperimentDetail,
  ExperimentSummary,
  ManufacturingContext,
  NodeVerdicts,
  PriorRecordDetail,
  PriorRecordSummary,
  PriorVerdict,
  Settings,
  SourceType,
  TurnResponse,
  WorkflowRecord,
  WorkflowSummary,
} from "./types";

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
  updateManufacturingContext: (id: string, patch: Partial<ManufacturingContext>) =>
    req<WorkflowRecord>("PUT", `/api/expert-workflows/${id}/manufacturing-context`, patch),

  getDraftPool: (sourceType: SourceType) =>
    req<{ source_type: SourceType; count: number }>("GET", `/api/datasets/draft-pool?source_type=${sourceType}`),
  publishDataset: (sourceType: SourceType, actorRole?: string) =>
    req<DatasetVersionSummary>("POST", "/api/datasets/publish", { source_type: sourceType, actor_role: actorRole }),
  archiveDatasetVersion: (versionId: string) =>
    req<DatasetVersionSummary>("POST", `/api/datasets/versions/${versionId}/archive`),
  markDatasetVersionGold: (versionId: string, isGold: boolean, actorRole?: string) =>
    req<DatasetVersionSummary>(
      "POST",
      `/api/datasets/versions/${versionId}/mark-gold?is_gold=${isGold}&actor_role=${encodeURIComponent(actorRole ?? "unknown")}`,
    ),
  listDatasetVersions: (sourceType: SourceType, includeArchived = false) =>
    req<DatasetVersionSummary[]>(
      "GET",
      `/api/datasets/versions?source_type=${sourceType}&include_archived=${includeArchived}`,
    ),

  listExperiments: () => req<ExperimentSummary[]>("GET", "/api/experiments"),
  createExperiment: (payload: CreateExperimentRequest) =>
    req<ExperimentDetail>("POST", "/api/experiments", payload),
  getExperiment: (id: string) => req<ExperimentDetail>("GET", `/api/experiments/${id}`),
  updateExplanation: (id: string, text: string) =>
    req<ExperimentDetail>("PUT", `/api/experiments/${id}/explanation`, { text }),
  regenerateExplanation: (id: string) =>
    req<ExperimentDetail>("POST", `/api/experiments/${id}/regenerate-explanation`),
  compareExperiments: (experimentIds: string[]) =>
    req<ComparisonResult>("POST", "/api/experiments/compare", { experiment_ids: experimentIds }),

  polishSpeech: (text: string) => req<{ text: string; polished: boolean }>("POST", "/api/voice/polish", { text }),

  getSettings: () => req<Settings>("GET", "/api/settings"),
  updateSettings: (patch: Record<string, unknown>) => req<Settings>("PUT", "/api/settings", patch),
  testConnection: (level: string) =>
    req<{ ok: boolean; message: string }>("POST", `/api/settings/llm-levels/${level}/test-connection`),

  getAuditLog: () => req<AuditLogEntry[]>("GET", "/api/admin/audit-log"),

  importPrecheck: (payload: unknown) => req<ImportPrecheckReport>("POST", "/api/datasets/import/precheck", payload),
  importConfirm: (payload: unknown, actorRole: string, importRecordsWithoutErrors: boolean) =>
    req<DatasetVersionSummary>("POST", "/api/datasets/import/confirm", {
      payload, actor_role: actorRole, import_records_without_errors: importRecordsWithoutErrors,
    }),
  exportVersionUrl: (versionId: string, format: string) => `${BASE}/api/datasets/versions/${versionId}/export?format=${format}`,
  drillDown: (versionId: string, dimension: string) =>
    req<{ dimension: string; score: number | null; problem_records: { record_id: string; name: string; reason: string }[] }>(
      "GET",
      `/api/datasets/versions/${versionId}/drill-down?dimension=${dimension}`,
    ),
  getSlice: (versionId: string, field: string) =>
    req<{ field: string; buckets: { value: string; count: number; pct: number }[] }>(
      "GET",
      `/api/datasets/versions/${versionId}/slice?field=${field}`,
    ),
  getTrend: (sourceType: SourceType) =>
    req<{ source_type: SourceType; points: TrendPoint[] }>("GET", `/api/datasets/trend?source_type=${sourceType}`),

  listPriorRecords: (versionId: string) =>
    req<PriorRecordSummary[]>("GET", `/api/datasets/versions/${versionId}/records`),
  getPriorRecord: (versionId: string, recordId: string) =>
    req<PriorRecordDetail>("GET", `/api/datasets/versions/${versionId}/records/${recordId}`),
  submitAnnotation: (
    versionId: string,
    recordId: string,
    verdict: PriorVerdict,
    nodeVerdicts: NodeVerdicts,
    note: string | null,
    annotatorName: string,
    actorRole?: string,
  ) =>
    req<PriorRecordDetail>("POST", `/api/datasets/versions/${versionId}/records/${recordId}/annotations`, {
      verdict, node_verdicts: nodeVerdicts, note, annotator_name: annotatorName, actor_role: actorRole,
    }),
  getAnnotationSummary: (versionId: string) =>
    req<AnnotationSummary>("GET", `/api/datasets/versions/${versionId}/annotation-summary`),
};

export interface ImportPrecheckReport {
  total_records: number;
  importable_records: number;
  error_count: number;
  warning_count: number;
  issues: { level: "error" | "warning"; code: string; message: string; record_id: string | null }[];
  preview_readiness: { overall: number | null } | null;
  gold_annotation_note: string;
  recommendation: string;
  text_threshold: number;
  structure_threshold: number;
  importable_record_ids: string[];
}

export interface TrendPoint {
  version_number: number;
  created_at: string;
  overall: number | null;
  dimensions: Record<string, number | null>;
}
