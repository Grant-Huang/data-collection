// Read-only renderings of annotations and rework revisions -- used by the arbitration
// side-by-side view, the rework "start from this suggestion" list, and the finished-record
// history. Never rendered during blind independent review (the backend doesn't even send the
// data then).
import type { ReactNode } from "react";
import type { Graph, PriorAnnotation, PriorRecordDetail, PriorVerdict } from "../../api/types";
import { REASON_TAG_LABELS, VERDICT_LABELS } from "../../api/types";
import { describeVerdict } from "../../utils/annotationAccess";

export const VERDICT_COLOR: Record<PriorVerdict, string> = {
  accepted: "#0ca30c", needs_revision: "#d99400", rejected: "#ec835a",
};

export function AnnotationCard({ a, graph, footer }: { a: PriorAnnotation; graph: Graph; footer?: ReactNode }) {
  const nodeEntries = Object.entries(a.node_verdicts).filter(([, v]) => v !== "keep");
  return (
    <div style={{ flex: 1, minWidth: 0, border: "1px solid #e5e7eb", borderRadius: 8, padding: "10px 12px", fontSize: 12 }}>
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
      {nodeEntries.length > 0 && (
        <ul style={{ margin: "0 0 6px", paddingLeft: 16, color: "#475569" }}>
          {nodeEntries.map(([id, v]) => (
            <li key={id}>
              「{graph.nodes.find((n) => n.node_id === id)?.label ?? id}」→ {describeVerdict(graph, v)}
            </li>
          ))}
        </ul>
      )}
      {a.note && <div style={{ color: "#667085" }}>备注：{a.note}</div>}
      {footer}
    </div>
  );
}

// Full history, grouped by round, with each rework revision between the rounds it connects.
export function RoundHistory({ detail }: { detail: PriorRecordDetail }) {
  if (detail.annotations.length === 0 && detail.revisions.length === 0) return null;
  const rounds = Array.from({ length: detail.round }, (_, i) => i + 1);
  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: "#667085", marginBottom: 8 }}>标注与返工历史</div>
      {rounds.map((r) => {
        const inRound = detail.annotations.filter((a) => (a.round ?? 1) === r);
        const revision = detail.revisions.find((rv) => rv.from_round === r);
        // Round r was judged on the original graph (r = 1) or on revision r-1's output.
        const graphForRound = r === 1 ? detail.original_graph : detail.revisions[r - 2]?.graph ?? detail.graph;
        return (
          <div key={r} style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 4 }}>第 {r} 轮</div>
            {inRound.length === 0 ? (
              <div style={{ fontSize: 12, color: "#94a3b8" }}>（本轮还没有标注）</div>
            ) : (
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {inRound.map((a) => (
                  <AnnotationCard key={a.annotation_id} a={a} graph={graphForRound} />
                ))}
              </div>
            )}
            {revision && (
              <div style={{ marginTop: 6, fontSize: 12, color: "#475569", background: "#f8fafc", borderRadius: 6, padding: "6px 10px" }}>
                ↳ 返工（{revision.reworker_name}）：
                {[
                  Object.values(revision.edits.node_verdicts).filter((v) => v !== "keep").length && `节点判定 ${Object.values(revision.edits.node_verdicts).filter((v) => v !== "keep").length} 处`,
                  Object.keys(revision.edits.renames).length && `改名 ${Object.keys(revision.edits.renames).length} 处`,
                  revision.edits.inserts.length && `插入步骤 ${revision.edits.inserts.length} 个`,
                ].filter(Boolean).join("，")}
                {revision.note && `——${revision.note}`}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
