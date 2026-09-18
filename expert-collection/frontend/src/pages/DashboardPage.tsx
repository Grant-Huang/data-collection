// PRD 13: desktop-only Dashboard. Phase 3 sub-scope (IMPLEMENTATION_PLAN.md section 6):
// expert_collected source only, quality-score tab fully built; trend/drill-down tabs and
// public_extracted are honest placeholders, not yet implemented.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { DIMENSION_LABELS, DIMENSION_ORDER, DIMENSION_WEIGHTS } from "../api/types";
import type { DatasetVersionSummary, SourceType } from "../api/types";
import { MetricCard } from "../components/MetricCard";
import { ScoreBar } from "../components/ScoreBar";

type Tab = "quality" | "completeness" | "leakage" | "trend";

const TABS: { key: Tab; label: string }[] = [
  { key: "quality", label: "质量评分" },
  { key: "completeness", label: "完整度明细" },
  { key: "leakage", label: "泄漏与重复" },
  { key: "trend", label: "趋势" },
];

const BAND_COLOR: Record<string, string> = { good: "#0ca30c", warning: "#fab219", poor: "#ec835a", insufficient_sample: "#94a3b8" };
const BAND_LABEL: Record<string, string> = { good: "良好", warning: "待改善", poor: "较差", insufficient_sample: "样本不足" };

export function DashboardPage() {
  const [sourceType, setSourceType] = useState<SourceType>("expert_collected");
  const [versions, setVersions] = useState<DatasetVersionSummary[]>([]);
  const [draftCount, setDraftCount] = useState(0);
  const [tab, setTab] = useState<Tab>("quality");
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (st: SourceType) => {
    try {
      const [vs, pool] = await Promise.all([api.listDatasetVersions(st), api.getDraftPool(st)]);
      setVersions(vs);
      setDraftCount(pool.count);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    refresh(sourceType);
  }, [sourceType, refresh]);

  async function handlePublish() {
    setPublishing(true);
    setError(null);
    try {
      await api.publishDataset(sourceType);
      await refresh(sourceType);
    } catch (e) {
      setError(String(e));
    } finally {
      setPublishing(false);
    }
  }

  const latest = versions[0] ?? null;
  const readiness = latest?.readiness ?? null;

  return (
    <div style={{ height: "100%", overflowY: "auto", background: "#f6f7f9" }}>
      <div style={{ maxWidth: 980, margin: "0 auto", padding: "20px 24px 60px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <h1 style={{ fontSize: 18, fontWeight: 800, margin: 0 }}>Dashboard</h1>
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
                  {st === "expert_collected" ? "专家集" : "公共集"}
                </button>
              ))}
            </div>
          </div>
          <div style={{ fontSize: 11.5, color: "#94a3b8" }}>
            {latest ? `最近更新: ${new Date(latest.created_at).toLocaleString("zh-CN")}` : "尚未发布任何版本"}
          </div>
        </div>

        {sourceType === "public_extracted" ? (
          <div style={{ background: "#fff", border: "1px dashed #d0d5dd", borderRadius: 10, padding: 32, textAlign: "center", color: "#94a3b8", fontSize: 13 }}>
            公共集导入尚未实现（Phase 3 下一轮范围），暂无数据可展示。
          </div>
        ) : (
          <>
            <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: "12px 16px", display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
              <div style={{ fontSize: 12.5, color: "#475569" }}>
                草稿池中有 <b>{draftCount}</b> 条已确认但尚未发布的采集记录
                {latest && <span style={{ color: "#94a3b8" }}>（当前版本 v{latest.version_number}，发布于 {new Date(latest.created_at).toLocaleDateString("zh-CN")}）</span>}
              </div>
              <button
                onClick={handlePublish}
                disabled={publishing || draftCount === 0}
                style={{
                  border: "none", borderRadius: 8, padding: "8px 16px", fontWeight: 600, fontSize: 12.5,
                  background: draftCount === 0 ? "#e5e7eb" : "#2a78d6", color: draftCount === 0 ? "#94a3b8" : "#fff",
                  cursor: draftCount === 0 ? "default" : "pointer",
                }}
              >
                {publishing ? "发布中…" : "发布新版本"}
              </button>
            </div>

            {!latest ? (
              <div style={{ background: "#fff", border: "1px dashed #d0d5dd", borderRadius: 10, padding: 32, textAlign: "center", color: "#94a3b8", fontSize: 13 }}>
                还没有发布过版本，先在专家采集页完成并确认几条会话，再回来发布。
              </div>
            ) : (
              <>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 10, marginBottom: 20 }}>
                  <MetricCard label="工作流数" value={latest.workflow_count} tip="当前版本包含的已确认专家会话数量。" />
                  <MetricCard label="步骤总数" value={latest.total_steps} tip="所有已采集工作流的节点总数之和，衡量数据集的体量，不只是条数。" />
                  <MetricCard label="微工作流识别数" value="待实现" placeholder tip="跨 3 条及以上工作流复用、结构相似度超过阈值的可复用子图数量。识别算法（结构化子图挖掘）尚未实现，先诚实占位，不编造数字。" />
                  <MetricCard label="专家数" value="待实现" placeholder tip="贡献过采集记录的专家人数。当前系统还没有真实的专家身份认证（见假设 1），暂无法统计。" />
                  <MetricCard label="Gold 数量" value={0} tip="经过人工标注确认的 Gold 样本数。标注体系尚未实现，固定为 0。" />
                  <MetricCard label="待复核" value={0} tip="被标记为需要人工复核的记录数。复核流程尚未实现，固定为 0。" />
                </div>

                <div style={{ display: "flex", gap: 4, borderBottom: "1px solid #e5e7eb", marginBottom: 16 }}>
                  {TABS.map((t) => (
                    <button
                      key={t.key}
                      onClick={() => setTab(t.key)}
                      style={{
                        border: "none", background: "none", padding: "8px 14px", fontSize: 13, cursor: "pointer",
                        color: tab === t.key ? "#2a78d6" : "#667085", fontWeight: tab === t.key ? 700 : 500,
                        borderBottom: tab === t.key ? "2px solid #2a78d6" : "2px solid transparent",
                      }}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>

                {tab === "quality" && readiness && (
                  <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20 }}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 4 }}>
                      <div style={{ fontSize: 13, color: "#667085" }}>Dataset Readiness Score</div>
                      {readiness.overall !== null ? (
                        <>
                          <div style={{ fontSize: 32, fontWeight: 800, color: BAND_COLOR[readiness.band] }}>{readiness.overall}</div>
                          <div style={{ fontSize: 12, fontWeight: 700, color: BAND_COLOR[readiness.band] }}>{BAND_LABEL[readiness.band]}</div>
                        </>
                      ) : (
                        <div style={{ fontSize: 16, fontWeight: 700, color: "#94a3b8" }}>
                          样本量不足（{readiness.sample_size}/20），暂不评分
                        </div>
                      )}
                    </div>
                    <div style={{ marginTop: 12 }}>
                      {DIMENSION_ORDER.map((key) => (
                        <ScoreBar
                          key={key}
                          dimensionKey={key}
                          label={DIMENSION_LABELS[key]}
                          weight={DIMENSION_WEIGHTS[key]}
                          dim={readiness.dimensions[key]}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {tab === "completeness" && (
                  <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20, fontSize: 13, color: "#94a3b8" }}>
                    完整度明细表复用"流程完整度"与"Graph 结构完整度"两个维度的子指标（见"质量评分"Tab 中对应行的解释弹窗），独立的下钻表格视图留到下一轮实现。
                  </div>
                )}
                {tab === "leakage" && (
                  <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20, fontSize: 13, color: "#94a3b8" }}>
                    当前"低泄漏风险"维度只用触发描述完全重复作为粗粒度信号（见"质量评分"Tab）。更精细的近重复检测表格（TF-IDF/MinHash 文本相似度、Graph Edit Distance 结构相似度）尚未实现，留到下一轮。
                  </div>
                )}
                {tab === "trend" && (
                  <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20, fontSize: 13, color: "#94a3b8" }}>
                    趋势视图需要多个历史版本的走势数据。当前只发布过 {versions.length} 个版本，随着后续多次发布积累数据后再实现这个 Tab 更有意义。
                  </div>
                )}
              </>
            )}
          </>
        )}

        {error && (
          <div style={{ marginTop: 16, background: "#fef2f2", border: "1px solid #fecaca", color: "#991b1b", borderRadius: 8, padding: "8px 12px", fontSize: 12 }}>
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
