// 「数据录入与标注」页的「数据标注」tab -- 从 DashboardPage 挪过来（之前是嵌在 Dashboard 首屏
// 里的一块），入口是这里列出的记录清单（“从清单入口，非全”：一条条进，不是一个“全部标注”的
// 批量入口），点「去标注」打开 PriorAnnotationPanel。按来源（专家集/公有集）区分，跟 Dashboard
// 页保持一致的分类，但这里只关心当前最新版本要标注的记录，不关心已发布版本历史——历史版本列表
// 是 Dashboard「查看全部」的事。
//
// 权限：未来应该根据角色只显示专家能看到自己需要标注的那部分（PRD 16.2 的精神），这一轮先不
// 做，两个来源、全部记录对当前身份一样可见。
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { GOLD_STATUS_LABELS, VERDICT_LABELS } from "../api/types";
import type { AnnotationSummary, PriorRecordSummary, Role, SourceType } from "../api/types";
import { PriorAnnotationPanel } from "../components/PriorAnnotationPanel";

export function AnnotationTab({ role }: { role: Role }) {
  const [sourceType, setSourceType] = useState<SourceType>("expert_collected");
  const [latestVersionId, setLatestVersionId] = useState<string | null>(null);
  const [priorRecords, setPriorRecords] = useState<PriorRecordSummary[]>([]);
  const [annotationSummary, setAnnotationSummary] = useState<AnnotationSummary | null>(null);
  const [annotatingRecordId, setAnnotatingRecordId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (st: SourceType) => {
    setError(null);
    try {
      const versions = await api.listDatasetVersions(st);
      const latestId = versions[0]?.id ?? null;
      setLatestVersionId(latestId);
      if (latestId) {
        const [records, summary] = await Promise.all([
          api.listPriorRecords(latestId),
          api.getAnnotationSummary(latestId),
        ]);
        setPriorRecords(records);
        setAnnotationSummary(summary);
      } else {
        setPriorRecords([]);
        setAnnotationSummary(null);
      }
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    refresh(sourceType);
  }, [sourceType, refresh]);

  return (
    <div style={{ height: "100%", overflowY: "auto", background: "#f6f7f9" }}>
      <div style={{ maxWidth: 980, margin: "0 auto", padding: "20px 24px 60px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 16 }}>
          <h1 style={{ fontSize: 18, fontWeight: 800, margin: 0 }}>数据标注</h1>
          <div style={{ display: "flex", border: "1px solid #d0d5dd", borderRadius: 999, overflow: "hidden", fontSize: 12.5 }}>
            {(["expert_collected", "public_extracted"] as SourceType[]).map((st) => (
              <button
                key={st}
                onClick={() => setSourceType(st)}
                style={{
                  border: "none", padding: "6px 14px", cursor: "pointer",
                  background: sourceType === st ? "#2a78d6" : "#fff",
                  color: sourceType === st ? "#fff" : "#475569", fontWeight: 600,
                }}
              >
                {st === "expert_collected" ? "专家集" : "公有集"}
              </button>
            ))}
          </div>
        </div>

        {!latestVersionId ? (
          <div style={{ background: "#fff", border: "1px dashed #d0d5dd", borderRadius: 10, padding: 32, textAlign: "center", color: "#94a3b8", fontSize: 13 }}>
            {sourceType === "expert_collected" ? "还没有发布过版本，先在「专家录入」完成并确认几条会话，发布后再回来标注。" : "还没有导入过公有集数据。"}
          </div>
        ) : priorRecords.length === 0 ? (
          <div style={{ background: "#fff", border: "1px dashed #d0d5dd", borderRadius: 10, padding: 32, textAlign: "center", color: "#94a3b8", fontSize: 13 }}>
            当前最新版本没有可标注的记录。
          </div>
        ) : (
          <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 700 }}>
                {sourceType === "public_extracted" ? "Prior 标注（Public/LLM-derived Prior → Expert-annotated Prior）" : "专家复核（独立第二人确认 → Gold）"}
              </div>
              {annotationSummary && (
                <div style={{ fontSize: 11.5, color: "#94a3b8" }}>
                  标注覆盖率 {annotationSummary.annotated_records}/{annotationSummary.total_records}
                  {annotationSummary.annotated_records > 0 && (
                    <span>
                      {" "}
                      （{(["accepted", "needs_revision", "rejected"] as const)
                        .filter((v) => annotationSummary.verdict_counts[v])
                        .map((v) => `${VERDICT_LABELS[v]} ${annotationSummary.verdict_counts[v]}`)
                        .join("，")}
                      ）
                    </span>
                  )}
                  {" ・ "}Gold {annotationSummary.gold_counts.gold ?? 0} 条
                  {annotationSummary.agreement_kappa !== null && ` ・ 一致性 κ=${annotationSummary.agreement_kappa}`}
                </div>
              )}
            </div>
            <div>
              {priorRecords.map((r) => (
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
      </div>

      {annotatingRecordId && latestVersionId && (
        <PriorAnnotationPanel
          versionId={latestVersionId}
          recordId={annotatingRecordId}
          role={role}
          onClose={() => setAnnotatingRecordId(null)}
          onSaved={() => refresh(sourceType)}
        />
      )}
    </div>
  );
}
