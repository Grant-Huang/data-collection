// 数据与实验管理: dataset-related config (import/export, quality & publish params) and
// experiment run params, split into their own tabs instead of one flat admin page. Only
// reachable when role === "admin" (see DesktopApp's NAV minRole gating) -- the same
// front-end role-gating this app already uses in place of a real permission system (no
// account system exists yet, see IMPLEMENTATION_PLAN.md section 7).
import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { api } from "../api/client";
import type { DatasetVersionSummary, Settings, SourceType } from "../api/types";
import { ImportPanel } from "../components/ImportPanel";
import { PillTabs, UnderlineTabs } from "../components/TabBar";
import { TipIcon } from "../components/TipIcon";

type MainTab = "dataset" | "experiment";
type DatasetSubTab = "import_export" | "quality_params";

const MAIN_TABS: { key: MainTab; label: string }[] = [
  { key: "dataset", label: "数据集管理" },
  { key: "experiment", label: "实验设置" },
];

const DATASET_SUB_TABS: { key: DatasetSubTab; label: string }[] = [
  { key: "import_export", label: "导入 / 导出" },
  { key: "quality_params", label: "质量与发布参数" },
];

const SOURCE_TYPE_TABS: { key: SourceType; label: string }[] = [
  { key: "expert_collected", label: "专家集" },
  { key: "public_extracted", label: "公共集" },
];

const EXPORT_FORMATS: { key: string; label: string }[] = [
  { key: "raw", label: "原始版" }, { key: "role_normalized", label: "角色归一化版" }, { key: "anonymized", label: "匿名版" },
];

export function DataExperimentManagementPage() {
  const [mainTab, setMainTab] = useState<MainTab>("dataset");
  const [datasetSubTab, setDatasetSubTab] = useState<DatasetSubTab>("import_export");
  const [settings, setSettings] = useState<Settings | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sourceType, setSourceType] = useState<SourceType>("public_extracted");
  const [versions, setVersions] = useState<DatasetVersionSummary[]>([]);

  useEffect(() => {
    api.getSettings().then(setSettings).catch((e) => setError(String(e)));
  }, []);

  const refreshVersions = useCallback(async (st: SourceType) => {
    setVersions(await api.listDatasetVersions(st));
  }, []);

  useEffect(() => {
    refreshVersions(sourceType);
  }, [sourceType, refreshVersions]);

  async function saveQualityParams(patch: Record<string, unknown>) {
    if (!settings) return;
    setSaving(true);
    try {
      setSettings(await api.updateSettings({ quality_params: patch }));
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function saveRunParams(patch: Record<string, unknown>) {
    if (!settings) return;
    setSaving(true);
    try {
      setSettings(await api.updateSettings({ run_params: patch }));
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  const latest = versions[0] ?? null;

  return (
    <div style={{ height: "100%", overflowY: "auto", background: "#f6f7f9" }}>
      <div style={{ maxWidth: 760, margin: "0 auto", padding: "20px 24px 60px" }}>
        <h1 style={{ fontSize: 18, fontWeight: 800, marginTop: 0 }}>数据与实验管理</h1>
        {saving && <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 8 }}>保存中…</div>}

        <UnderlineTabs tabs={MAIN_TABS} active={mainTab} onChange={setMainTab} />

        {mainTab === "dataset" && (
          <>
            <div style={{ marginBottom: 16 }}>
              <PillTabs tabs={DATASET_SUB_TABS} active={datasetSubTab} onChange={setDatasetSubTab} />
            </div>

            {datasetSubTab === "import_export" && (
              <section style={sectionCard}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                  <div style={sectionTitle}>数据集导入 / 导出</div>
                  <PillTabs tabs={SOURCE_TYPE_TABS} active={sourceType} onChange={setSourceType} />
                </div>

                {sourceType === "public_extracted" && (
                  <div style={{ marginBottom: 16 }}>
                    <ImportPanel role="admin" onImported={() => refreshVersions(sourceType)} />
                  </div>
                )}

                <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 8 }}>
                  导出当前版本{latest ? `（v${latest.version_number}）` : ""}：
                </div>
                {latest ? (
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {EXPORT_FORMATS.map((f) => (
                      <a
                        key={f.key}
                        href={api.exportVersionUrl(latest.id, f.key)}
                        style={{ fontSize: 11.5, color: "#2a78d6", border: "1px solid #d0d5dd", borderRadius: 6, padding: "4px 10px", textDecoration: "none" }}
                      >
                        {f.label}
                      </a>
                    ))}
                  </div>
                ) : (
                  <div style={{ fontSize: 12, color: "#94a3b8" }}>该数据源尚未发布过版本，暂无可导出内容。</div>
                )}
              </section>
            )}

            {datasetSubTab === "quality_params" && settings && (
              <section style={sectionCard}>
                <div style={sectionTitle}>质量评分与发布参数</div>
                <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 12 }}>
                  前两项真实生效——改动只影响下一次发布/计算，不会补算历史分数（PRD 17.4）。后三项（Completion Score 完成门槛、发布提示阈值）目前只是存起来，还没有接到任何实际判断逻辑上，属于预留参数。
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <NumberField
                    label="小样本评分阈值（条）"
                    value={settings.quality_params.min_sample_size}
                    tip="数据集记录数低于这个数量时，Dashboard 不计算总体质量分——样本太少时分数波动大，容易误导判断，这时会诚实显示「样本量不足，暂不评分」。"
                    onSave={(v) => saveQualityParams({ min_sample_size: v })}
                  />
                  <NumberField
                    label="近重复文本相似度阈值"
                    value={settings.quality_params.near_dup_text_threshold}
                    step={0.01}
                    tip="导入公共集时，两条记录的触发场景描述文本相似度（Jaccard）超过这个阈值（0~1，越接近 1 要求越像）就会被标记为疑似近重复，提示人工复核，但不会自动拦截导入。"
                    onSave={(v) => saveQualityParams({ near_dup_text_threshold: v })}
                  />
                  <NumberField
                    label="Completion Score 完成门槛"
                    value={settings.quality_params.completion_threshold}
                    tip="预留参数：按命名意图，本应是专家采集会话完成度分数（0~100）的达标门槛。当前会话能否确认实际由采集流程的 review 阶段和 Graph 结构校验决定，不读这个数字——改这里暂时不会影响任何行为。"
                    onSave={(v) => saveQualityParams({ completion_threshold: v })}
                  />
                  <NumberField
                    label="数据集发布提示阈值（新增条数）"
                    value={settings.quality_params.publish_prompt_count}
                    tip="预留参数：按命名意图，本应是草稿池新增记录数达到这个条数时提醒「可以发布新版本了」。当前界面还没有实现这个提醒，改这里暂时不会影响任何行为。"
                    onSave={(v) => saveQualityParams({ publish_prompt_count: v })}
                  />
                  <NumberField
                    label="数据集发布提示阈值（天数）"
                    value={settings.quality_params.publish_prompt_days}
                    tip="预留参数：按命名意图，本应是距上次发布超过这个天数就提醒该发布新版本了。当前界面还没有实现这个提醒，改这里暂时不会影响任何行为。"
                    onSave={(v) => saveQualityParams({ publish_prompt_days: v })}
                  />
                </div>
              </section>
            )}
          </>
        )}

        {mainTab === "experiment" && settings && (
          <section style={sectionCard}>
            <div style={sectionTitle}>实验运行参数</div>
            <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 12 }}>
              这两项目前只是存起来，还没有接到实验执行逻辑上（当前实验是同步顺序执行，没有并发调度，也没有超时强制终止），属于预留参数。
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <NumberField
                label="并发实验数上限"
                value={settings.run_params.max_concurrent_experiments}
                tip="预留参数：按命名意图，本应限制系统同时执行的实验 Run 数量。当前实验是逐个同步执行的，没有并发调度，改这里暂时不会影响任何行为。"
                onSave={(v) => saveRunParams({ max_concurrent_experiments: v })}
              />
              <NumberField
                label="单次 Run 超时时间（秒）"
                value={settings.run_params.run_timeout_seconds}
                tip="预留参数：按命名意图，本应是单次实验运行超过这个秒数就强制标记失败。当前没有超时强制终止逻辑，改这里暂时不会影响任何行为。"
                onSave={(v) => saveRunParams({ run_timeout_seconds: v })}
              />
            </div>
          </section>
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

function NumberField({ label, value, step, tip, onSave }: { label: string; value: number; step?: number; tip?: string; onSave: (v: number) => void }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
      <div style={{ width: 200, fontSize: 12.5, color: "#374151", fontWeight: 600, flexShrink: 0, display: "flex", alignItems: "center" }}>
        {label}
        {tip && <TipIcon text={tip} />}
      </div>
      <input type="number" step={step ?? 1} defaultValue={value} onBlur={(e) => onSave(Number(e.target.value))} style={inputStyle} />
    </div>
  );
}

const sectionCard: CSSProperties = { background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20, marginBottom: 16 };
const sectionTitle: CSSProperties = { fontSize: 14, fontWeight: 800, margin: "0 0 12px" };
const inputStyle: CSSProperties = { border: "1px solid #d0d5dd", borderRadius: 6, padding: "7px 10px", fontSize: 12.5 };
