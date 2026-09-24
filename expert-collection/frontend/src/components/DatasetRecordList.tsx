// Extracted from AnnotationTab.tsx so a specific dataset version's record list can be shown
// from more than one entry point: AnnotationTab still only ever looks at each source's latest
// version, but Dashboard's "全部数据集版本 -> 查看" needs the same list for whichever (possibly
// historical) version the user picked there -- previously that button just re-opened the
// Dashboard's own score summary screen instead of drilling into the version's actual records.
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api } from "../api/client";
import { GOLD_STATUS_LABELS, VERDICT_LABELS } from "../api/types";
import type { AnnotationSummary, PriorRecordSummary, Role } from "../api/types";
import { PriorAnnotationPanel } from "./PriorAnnotationPanel";

interface Props {
  versionId: string;
  role: Role;
  title?: ReactNode;
  emptyMessage?: string;
}

export function DatasetRecordList({ versionId, role, title, emptyMessage }: Props) {
  const [records, setRecords] = useState<PriorRecordSummary[]>([]);
  const [summary, setSummary] = useState<AnnotationSummary | null>(null);
  const [annotatingRecordId, setAnnotatingRecordId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [recs, sum] = await Promise.all([
        api.listPriorRecords(versionId),
        api.getAnnotationSummary(versionId),
      ]);
      setRecords(recs);
      setSummary(sum);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [versionId]);

  useEffect(() => {
    setLoading(true);
    refresh();
  }, [refresh]);

  return (
    <div>
      {loading ? (
        <div style={{ background: "#fff", border: "1px dashed #d0d5dd", borderRadius: 10, padding: 32, textAlign: "center", color: "#94a3b8", fontSize: 13 }}>
          加载中…
        </div>
      ) : records.length === 0 ? (
        <div style={{ background: "#fff", border: "1px dashed #d0d5dd", borderRadius: 10, padding: 32, textAlign: "center", color: "#94a3b8", fontSize: 13 }}>
          {emptyMessage ?? "这个版本没有可查看的记录。"}
        </div>
      ) : (
        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            {title && <div style={{ fontSize: 13, fontWeight: 700 }}>{title}</div>}
            {summary && (
              <div style={{ fontSize: 11.5, color: "#94a3b8" }}>
                标注覆盖率 {summary.annotated_records}/{summary.total_records}
                {summary.annotated_records > 0 && (
                  <span>
                    {" "}
                    （{(["accepted", "needs_revision", "rejected"] as const)
                      .filter((v) => summary.verdict_counts[v])
                      .map((v) => `${VERDICT_LABELS[v]} ${summary.verdict_counts[v]}`)
                      .join("，")}
                    ）
                  </span>
                )}
                {" ・ "}Gold {summary.gold_counts.gold ?? 0} 条
                {summary.agreement_kappa !== null && ` ・ 一致性 κ=${summary.agreement_kappa}`}
              </div>
            )}
          </div>
          <div>
            {records.map((r) => (
              <div key={r.record_id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #f1f3f5" }}>
                <div style={{ fontSize: 12.5 }}>
                  {r.name} <span style={{ color: "#94a3b8" }}>（{r.node_count} 节点）</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span
                    style={{
                      fontSize: 11, fontWeight: 600, borderRadius: 999, padding: "2px 10px",
                      background: r.prior_status === "expert_annotated" ? "#eafaea" : "#f1f5f9",
                      color: r.prior_status === "expert_annotated" ? "#0ca30c" : "#667085",
                    }}
                  >
                    {r.prior_status === "expert_annotated" ? `已标注・${r.latest_verdict ? VERDICT_LABELS[r.latest_verdict] : ""}` : "待标注"}
                  </span>
                  <span
                    style={{
                      fontSize: 11, fontWeight: 600, borderRadius: 999, padding: "2px 10px",
                      background: r.gold_status === "gold" ? "#fff7e6" : "#f1f5f9",
                      color: r.gold_status === "gold" ? "#b45309" : "#667085",
                    }}
                  >
                    {GOLD_STATUS_LABELS[r.gold_status]}
                  </span>
                  <button
                    onClick={() => setAnnotatingRecordId(r.record_id)}
                    style={{ border: "1px solid #2a78d6", color: "#2a78d6", background: "#fff", borderRadius: 6, padding: "4px 12px", fontSize: 11.5, cursor: "pointer" }}
                  >
                    去标注
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {error && (
        <div style={{ marginTop: 16, background: "#fef2f2", border: "1px solid #fecaca", color: "#991b1b", borderRadius: 8, padding: "8px 12px", fontSize: 12 }}>
          {error}
        </div>
      )}

      {annotatingRecordId && (
        <PriorAnnotationPanel
          versionId={versionId}
          recordId={annotatingRecordId}
          role={role}
          onClose={() => setAnnotatingRecordId(null)}
          onSaved={refresh}
        />
      )}
    </div>
  );
}
