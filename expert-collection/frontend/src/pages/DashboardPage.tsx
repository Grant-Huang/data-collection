// PRD 13: desktop-only Dashboard. Phase 6 (IMPLEMENTATION_PLAN.md section 8) fills in real
// public_extracted import, export, drill-down and trend -- see that section for what's still
// deferred (dual-source trend overlay). §14.4 Dataset Slice (industry/scenario cross-tabs)
// is implemented -- see the "slice" tab below.
import { useCallback, useEffect, useState } from "react";
import { api, type TrendPoint } from "../api/client";
import { DIMENSION_LABELS, DIMENSION_ORDER, DIMENSION_WEIGHTS, SLICEABLE_FIELDS } from "../api/types";
import type { DatasetVersionSummary, Role, SourceType } from "../api/types";
import { MetricCard } from "../components/MetricCard";
import { ScoreBar } from "../components/ScoreBar";
import { TrendChart } from "../components/TrendChart";
import { DatasetVersionListPage } from "../components/DatasetVersionListPage";
import { DatasetRecordList } from "../components/DatasetRecordList";

// 专家标注/Prior 标注的入口 tab 已经挪到「数据录入与标注 → 数据标注」（见 pages/AnnotationTab.tsx），
// Dashboard 首屏只管发布/评分/导出；但「全部数据集版本 -> 查看」需要看某个（可能是历史）版本
// 具体有哪些记录，于是复用同一份 <DatasetRecordList> 组件（见该文件顶部注释），不是重新嵌一套。

type Screen = "dashboard" | "all_versions" | "version_records";
type Tab = "quality" | "completeness" | "leakage" | "trend" | "slice";

const TABS: { key: Tab; label: string }[] = [
  { key: "quality", label: "质量评分" },
  { key: "completeness", label: "完整度明细" },
  { key: "leakage", label: "泄漏与重复" },
  { key: "trend", label: "趋势" },
  { key: "slice", label: "行业/场景切片" },
];

const BAND_COLOR: Record<string, string> = { good: "#0ca30c", warning: "#fab219", poor: "#ec835a", insufficient_sample: "#94a3b8" };
const BAND_LABEL: Record<string, string> = { good: "良好", warning: "待改善", poor: "较差", insufficient_sample: "样本不足" };

export function DashboardPage({ role }: { role: Role }) {
  const [sourceType, setSourceType] = useState<SourceType>("expert_collected");
  const [screen, setScreen] = useState<Screen>("dashboard");
  const [versions, setVersions] = useState<DatasetVersionSummary[]>([]);
  const [draftCount, setDraftCount] = useState(0);
  const [tab, setTab] = useState<Tab>("quality");
  const [publishing, setPublishing] = useState(false);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  // null 代表首屏默认行为：看最新版本的质量评分。
  const [selectedVersion, setSelectedVersion] = useState<DatasetVersionSummary | null>(null);
  // 「全部数据集版本」列表里点「查看」时设置，切到 "version_records" 屏显示这个版本的具体
  // 记录清单（不是回到首屏的质量评分汇总——那不是「查看」这个版本该去的地方）。
  const [viewingVersion, setViewingVersion] = useState<DatasetVersionSummary | null>(null);
  const [sliceField, setSliceField] = useState<string>(SLICEABLE_FIELDS[0].field);
  const [sliceBuckets, setSliceBuckets] = useState<{ value: string; count: number; pct: number }[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (st: SourceType) => {
    try {
      const [vs, pool, trendRes] = await Promise.all([
        api.listDatasetVersions(st),
        st === "expert_collected" ? api.getDraftPool(st) : Promise.resolve({ count: 0 }),
        api.getTrend(st),
      ]);
      setVersions(vs);
      setDraftCount(pool.count);
      setTrend(trendRes.points);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    refresh(sourceType);
    setSelectedVersion(null);
    setViewingVersion(null);
    setScreen("dashboard");
  }, [sourceType, refresh]);

  useEffect(() => {
    const versionId = versions[0]?.id;
    if (tab !== "slice" || !versionId) return;
    api.getSlice(versionId, sliceField)
      .then((res) => setSliceBuckets(res.buckets))
      .catch((e) => setError(String(e)));
  }, [tab, sliceField, versions]);

  async function handlePublish() {
    setPublishing(true);
    setError(null);
    try {
      await api.publishDataset(sourceType, role);
      setSelectedVersion(null); // 发布完新版本，回到看最新版本
      await refresh(sourceType);
    } catch (e) {
      setError(String(e));
    } finally {
      setPublishing(false);
    }
  }

  // 归档/标 Gold 之后，如果当前正看着的就是被改的这个版本（可能是从「全部」列表选进来的，
  // 不一定是最新版本），把它也刷新一遍，不然界面上的归档/Gold 状态会跟后端脱节。
  async function handleArchive(versionId: string) {
    setError(null);
    try {
      const updated = await api.archiveDatasetVersion(versionId);
      if (selectedVersion?.id === versionId) setSelectedVersion(updated);
      await refresh(sourceType);
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleToggleGold(versionId: string, nextIsGold: boolean) {
    setError(null);
    try {
      const updated = await api.markDatasetVersionGold(versionId, nextIsGold, role);
      if (selectedVersion?.id === versionId) setSelectedVersion(updated);
      await refresh(sourceType);
    } catch (e) {
      setError(String(e));
    }
  }

  const latest = selectedVersion ?? versions[0] ?? null;
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
                  {st === "expert_collected" ? "专家集" : "公有集"}
                </button>
              ))}
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ fontSize: 11.5, color: "#94a3b8" }}>
              {latest ? `最近更新: ${new Date(latest.created_at).toLocaleString("zh-CN")}` : "尚未发布任何版本"}
            </div>
            {screen === "dashboard" && (
              <button
                onClick={() => setScreen("all_versions")}
                style={{ border: "1px solid #d0d5dd", background: "#fff", color: "#475569", borderRadius: 6, padding: "5px 12px", fontSize: 12, cursor: "pointer" }}
              >
                查看全部 →
              </button>
            )}
          </div>
        </div>

        {screen === "all_versions" ? (
          <DatasetVersionListPage
            sourceType={sourceType}
            canManage={role === "admin"}
            actorRole={role}
            onBack={() => setScreen("dashboard")}
            onSelectVersion={(v) => {
              setViewingVersion(v);
              setScreen("version_records");
            }}
            onChanged={() => refresh(sourceType)}
          />
        ) : screen === "version_records" && viewingVersion ? (
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
              <button
                onClick={() => setScreen("all_versions")}
                style={{ border: "1px solid #d0d5dd", background: "#fff", color: "#475569", borderRadius: 6, padding: "5px 10px", fontSize: 12, cursor: "pointer" }}
              >
                ← 返回
              </button>
              <div style={{ fontSize: 13, fontWeight: 700 }}>
                v{viewingVersion.version_number} {viewingVersion.name}
              </div>
            </div>
            <DatasetRecordList versionId={viewingVersion.id} role={role} />
          </div>
        ) : (
        <>

        {sourceType === "expert_collected" && (
          <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: "12px 16px", display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <div style={{ fontSize: 12.5, color: "#475569" }}>
              草稿池中有 <b>{draftCount}</b> 条已确认但尚未发布的采集记录
              {latest && <span style={{ color: "#94a3b8" }}>（当前版本 v{latest.version_number}，发布于 {new Date(latest.created_at).toLocaleDateString("zh-CN")}）</span>}
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              {role === "admin" && latest && (
                <button
                  onClick={() => handleArchive(latest.id)}
                  style={{ border: "1px solid #d0d5dd", background: "#fff", color: "#667085", borderRadius: 8, padding: "8px 14px", fontSize: 12.5, cursor: "pointer" }}
                >
                  归档当前版本
                </button>
              )}
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
          </div>
        )}

        {!latest ? (
          <div style={{ background: "#fff", border: "1px dashed #d0d5dd", borderRadius: 10, padding: 32, textAlign: "center", color: "#94a3b8", fontSize: 13 }}>
            {sourceType === "expert_collected" ? "还没有发布过版本，先在「数据录入与标注 → 专家录入」完成并确认几条会话，再回来发布。" : "还没有导入过公有集数据，请前往「数据与实验管理」的导入/导出面板导入。"}
          </div>
        ) : (
          <>
            {(latest.is_gold || role === "admin") && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                {latest.is_gold && (
                  <span style={{ fontSize: 11, fontWeight: 700, borderRadius: 999, padding: "2px 10px", background: "#fff7e6", color: "#b45309" }}>
                    ★ Gold 版本
                  </span>
                )}
                {role === "admin" && (
                  <button
                    onClick={() => handleToggleGold(latest.id, !latest.is_gold)}
                    style={{ border: "1px solid #d0d5dd", background: "#fff", color: "#667085", borderRadius: 6, padding: "2px 10px", fontSize: 11, cursor: "pointer" }}
                  >
                    {latest.is_gold ? "取消 Gold 标记" : "标记为 Gold 版本"}
                  </button>
                )}
              </div>
            )}

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 10, marginBottom: 20 }}>
              <MetricCard label="工作流数" value={latest.workflow_count} tip="当前版本包含的记录数量。" />
              <MetricCard label="步骤总数" value={latest.total_steps} tip="所有工作流的节点总数之和，衡量数据集的体量，不只是条数。" />
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
                      样本量不足（{readiness.sample_size}/{(readiness.dimensions.coverage?.sub_indicators as { threshold?: number })?.threshold ?? "?"}），暂不评分
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
                      versionId={latest.id}
                    />
                  ))}
                </div>
              </div>
            )}

            {tab === "completeness" && (
              <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20, fontSize: 13, color: "#94a3b8" }}>
                完整度明细表复用"流程完整度"与"Graph 结构完整度"两个维度的子指标——在"质量评分"Tab 里点开对应行，可以看解释和"定位问题样本"。
              </div>
            )}
            {tab === "leakage" && (
              <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20, fontSize: 13, color: "#94a3b8" }}>
                当前"低泄漏风险"维度只用触发描述完全重复作为粗粒度信号（见"质量评分"Tab）。导入公有集时的近重复检测（文本 Jaccard 相似度 + 结构类型集合相似度）会在预检报告里展示更详细的成对比较结果。
              </div>
            )}
            {tab === "trend" && (
              <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20 }}>
                <TrendChart points={trend} />
              </div>
            )}
            {tab === "slice" && (
              <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20 }}>
                <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
                  {SLICEABLE_FIELDS.map((f) => (
                    <button
                      key={f.field}
                      onClick={() => setSliceField(f.field)}
                      style={{
                        border: sliceField === f.field ? "none" : "1px solid #d0d5dd",
                        borderRadius: 999, padding: "4px 12px", fontSize: 12, cursor: "pointer",
                        background: sliceField === f.field ? "#2a78d6" : "#fff",
                        color: sliceField === f.field ? "#fff" : "#475569",
                      }}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
                {!latest ? (
                  <div style={{ fontSize: 13, color: "#94a3b8" }}>还没有已发布的版本，无法切片。</div>
                ) : sliceBuckets.length === 0 ? (
                  <div style={{ fontSize: 13, color: "#94a3b8" }}>这个版本还没有记录。</div>
                ) : (
                  <div>
                    {sliceBuckets.map((b) => (
                      <div key={b.value} style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 0", borderBottom: "1px solid #f1f3f5" }}>
                        <div style={{ width: 180, fontSize: 12.5, color: b.value === "未填写" ? "#94a3b8" : "#1f2937" }}>{b.value}</div>
                        <div style={{ flex: 1, height: 8, background: "#f1f5f9", borderRadius: 4, overflow: "hidden" }}>
                          <div style={{ width: `${Math.round(b.pct * 100)}%`, height: "100%", background: "#2a78d6" }} />
                        </div>
                        <div style={{ width: 70, textAlign: "right", fontSize: 12, color: "#667085" }}>{b.count} 条・{Math.round(b.pct * 100)}%</div>
                      </div>
                    ))}
                  </div>
                )}
                <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 12 }}>
                  切片依据每条记录的 manufacturing_context（导入公有集时已随记录一起校验；专家录入的工作流可在会话页顶部补填）。"未填写"是诚实的空值分组，不是缺陷。
                </div>
              </div>
            )}
          </>
        )}

        {error && (
          <div style={{ marginTop: 16, background: "#fef2f2", border: "1px solid #fecaca", color: "#991b1b", borderRadius: 8, padding: "8px 12px", fontSize: 12 }}>
            {error}
          </div>
        )}
        </>
        )}
      </div>
    </div>
  );
}
