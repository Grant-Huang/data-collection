// Read-only renderings of finished annotations (verdict, reasons, what was changed) and the
// per-round history -- shown once a record reaches arbitration or done. Never rendered during
// blind independent review (the backend doesn't even send the data then).
import type { PriorAnnotation, PriorRecordDetail, PriorVerdict } from "../../api/types";
import { REASON_TAG_LABELS, VERDICT_LABELS } from "../../api/types";

export const VERDICT_COLOR: Record<PriorVerdict, string> = {
  accepted: "#0ca30c", needs_revision: "#d99400", rejected: "#ec835a",
};

export function AnnotationCard({ a }: { a: PriorAnnotation }) {
  return (
    <div style={{ flex: 1, minWidth: 220, border: "1px solid #e5e7eb", borderRadius: 8, padding: "10px 12px", fontSize: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontWeight: 700 }}>
          {a.annotator_name}
          <span style={{ color: "#94a3b8", fontWeight: 400 }}>{a.role_in_process === "arbitration" ? "・仲裁" : "・独立标注"}</span>
        </span>
        <span style={{ color: VERDICT_COLOR[a.verdict], fontWeight: 700 }}>{VERDICT_LABELS[a.verdict]}</span>
      </div>
      {a.reason_tags.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 6 }}>
          {a.reason_tags.map((t) => (
            <span key={t} style={{ background: "#f1f5f9", color: "#475569", borderRadius: 999, padding: "1px 8px", fontSize: 11 }}>
              {REASON_TAG_LABELS[t]}
            </span>
          ))}
        </div>
      )}
      {a.changes && a.changes.length > 0 ? (
        <ul style={{ margin: 0, paddingLeft: 16, color: "#475569" }}>
          {a.changes.map((c, i) => <li key={i}>{c}</li>)}
        </ul>
      ) : (
        a.note && <div style={{ color: "#667085" }}>备注：{a.note}</div>
      )}
    </div>
  );
}

// Full history, grouped by round (rounds > 1 only exist for legacy section-16 rework data).
export function RoundHistory({ detail }: { detail: PriorRecordDetail }) {
  if (detail.annotations.length === 0) return null;
  const rounds = Array.from({ length: detail.round }, (_, i) => i + 1);
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: "#667085", marginBottom: 8 }}>标注记录</div>
      {rounds.map((r) => {
        const inRound = detail.annotations.filter((a) => (a.round ?? 1) === r);
        const revision = detail.revisions.find((rv) => rv.from_round === r);
        if (inRound.length === 0 && !revision) return null;
        return (
          <div key={r} style={{ marginBottom: 10 }}>
            {detail.round > 1 && <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 4 }}>第 {r} 轮</div>}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {inRound.map((a) => <AnnotationCard key={a.annotation_id} a={a} />)}
            </div>
            {revision && (
              <div style={{ marginTop: 6, fontSize: 12, color: "#475569", background: "#f8fafc", borderRadius: 6, padding: "6px 10px" }}>
                ↳ 返工（{revision.reworker_name}）{revision.note ? `：${revision.note}` : ""}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
