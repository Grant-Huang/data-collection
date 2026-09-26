// Extracted from AnnotationTab.tsx so a specific dataset version's record list can be shown
// from more than one entry point: AnnotationTab still only ever looks at each source's latest
// version, but Dashboard's "全部数据集版本 -> 查看" needs the same list for whichever (possibly
// historical) version the user picked there -- previously that button just re-opened the
// Dashboard's own score summary screen instead of drilling into the version's actual records.
//
// This component only loads the data; the list itself (stage filters, "我可处理" queue,
// progress, blind-review-safe status tags) and the annotation panel live in AnnotationQueue
// (IMPLEMENTATION_PLAN.md section 16), so both entry points get the same workflow.
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api, apiErrorMessage } from "../api/client";
import type { AnnotationSummary, PriorRecordSummary, Role } from "../api/types";
import { AnnotationQueue } from "./AnnotationQueue";

interface Props {
  versionId: string;
  role: Role;
  title?: ReactNode;
  emptyMessage?: string;
}

export function DatasetRecordList({ versionId, role, title, emptyMessage }: Props) {
  const [records, setRecords] = useState<PriorRecordSummary[]>([]);
  const [summary, setSummary] = useState<AnnotationSummary | null>(null);
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
      setError(apiErrorMessage(e));
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
        <AnnotationQueue title={title} versionId={versionId} records={records} summary={summary} role={role} onChanged={refresh} />
      )}

      {error && (
        <div style={{ marginTop: 16, background: "#fef2f2", border: "1px solid #fecaca", color: "#991b1b", borderRadius: 8, padding: "8px 12px", fontSize: 12 }}>
          {error}
        </div>
      )}
    </div>
  );
}
