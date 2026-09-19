// PRD 17: real CRUD form. See app/settings.py's docstring / IMPLEMENTATION_PLAN.md
// assumption 6 -- saving a config here does not yet switch any Mock service's behavior
// (no reachable inference service in this sandbox); the quality/run params DO take effect.
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { api } from "../api/client";
import { LLM_SLOT_LABELS, type LlmSlotConfig, type Settings } from "../api/types";

const CATEGORY_LABEL: Record<string, string> = { L: "L（本地 7B）", C_standard: "C-标准档", C_flagship: "C-旗舰档" };

export function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [testResults, setTestResults] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getSettings().then(setSettings).catch((e) => setError(String(e)));
  }, []);

  async function saveLlmSlot(slot: string, patch: Partial<LlmSlotConfig>) {
    if (!settings) return;
    setSaving(true);
    try {
      const updated = await api.updateSettings({ llm_configs: { [slot]: patch } });
      setSettings(updated);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

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

  async function handleTestConnection(slot: string) {
    const res = await api.testConnection(slot);
    setTestResults((prev) => ({ ...prev, [slot]: res.message }));
  }

  if (!settings) return null;

  return (
    <div style={{ height: "100%", overflowY: "auto", background: "#f6f7f9" }}>
      <div style={{ maxWidth: 760, margin: "0 auto", padding: "20px 24px 60px" }}>
        <h1 style={{ fontSize: 18, fontWeight: 800, marginTop: 0 }}>系统设置</h1>
        {saving && <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 8 }}>保存中…</div>}

        <section style={sectionCard}>
          <h2 style={sectionTitle}>LLM 模型配置</h2>
          <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 12 }}>
            每个环节独立配置，互不绑定（PRD 17.2）。当前环境没有可达的推理服务，"测试连接"会如实反馈，不会伪造成功。
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {Object.entries(settings.llm_configs).map(([slot, cfg]) => (
              <LlmSlotCard
                key={slot}
                slot={slot}
                cfg={cfg}
                onSave={(patch) => saveLlmSlot(slot, patch)}
                onTest={() => handleTestConnection(slot)}
                testResult={testResults[slot]}
              />
            ))}
          </div>
        </section>

        <section style={sectionCard}>
          <h2 style={sectionTitle}>语音识别配置（V 类）</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <FieldRow label="Workspace ID">
              <input
                defaultValue={settings.voice.workspace_id}
                onBlur={(e) => api.updateSettings({ voice: { workspace_id: e.target.value } }).then(setSettings)}
                style={inputStyle}
              />
            </FieldRow>
            <FieldRow label="Realtime 模型">
              <input
                defaultValue={settings.voice.realtime_model}
                onBlur={(e) => api.updateSettings({ voice: { realtime_model: e.target.value } }).then(setSettings)}
                style={inputStyle}
              />
            </FieldRow>
            <div style={{ fontSize: 11, color: "#94a3b8" }}>
              音色：不适用——本产品 AI 回复为文字，不出声（PRD 2.1/17.3）。
            </div>
          </div>
        </section>

        <section style={sectionCard}>
          <h2 style={sectionTitle}>质量评分与检测参数</h2>
          <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 12 }}>
            这些参数真实生效——改动只影响下一次发布/计算，不会补算历史分数（PRD 17.4）。
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <NumberField label="小样本评分阈值（条）" value={settings.quality_params.min_sample_size} onSave={(v) => saveQualityParams({ min_sample_size: v })} />
            <NumberField label="近重复文本相似度阈值" value={settings.quality_params.near_dup_text_threshold} step={0.01} onSave={(v) => saveQualityParams({ near_dup_text_threshold: v })} />
            <NumberField label="Completion Score 完成门槛" value={settings.quality_params.completion_threshold} onSave={(v) => saveQualityParams({ completion_threshold: v })} />
            <NumberField label="数据集发布提示阈值（新增条数）" value={settings.quality_params.publish_prompt_count} onSave={(v) => saveQualityParams({ publish_prompt_count: v })} />
            <NumberField label="数据集发布提示阈值（天数）" value={settings.quality_params.publish_prompt_days} onSave={(v) => saveQualityParams({ publish_prompt_days: v })} />
          </div>
        </section>

        <section style={sectionCard}>
          <h2 style={sectionTitle}>其他运行参数</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <NumberField label="并发实验数上限" value={settings.run_params.max_concurrent_experiments} onSave={(v) => saveRunParams({ max_concurrent_experiments: v })} />
            <NumberField label="单次 Run 超时时间（秒）" value={settings.run_params.run_timeout_seconds} onSave={(v) => saveRunParams({ run_timeout_seconds: v })} />
            <NumberField label="审计日志保留期限（天）" value={settings.run_params.audit_log_retention_days} onSave={(v) => saveRunParams({ audit_log_retention_days: v })} />
          </div>
        </section>

        {error && (
          <div style={{ background: "#fef2f2", border: "1px solid #fecaca", color: "#991b1b", borderRadius: 8, padding: "8px 12px", fontSize: 12 }}>
            {error}
          </div>
        )}
      </div>
    </div>
  );
}

function LlmSlotCard({ slot, cfg, onSave, onTest, testResult }: { slot: string; cfg: LlmSlotConfig; onSave: (patch: Partial<LlmSlotConfig>) => void; onTest: () => void; testResult?: string }) {
  const [category, setCategory] = useState(cfg.category);
  const [endpoint, setEndpoint] = useState(cfg.endpoint ?? "");
  const [modelName, setModelName] = useState(cfg.model_name ?? "");
  const [apiKey, setApiKey] = useState("");
  const [temperature, setTemperature] = useState(cfg.temperature ?? 0.2);

  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 8, padding: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <div style={{ fontSize: 13, fontWeight: 700 }}>{LLM_SLOT_LABELS[slot] ?? slot}</div>
        <select value={category} onChange={(e) => setCategory(e.target.value)} style={{ ...inputStyle, width: 140 }}>
          {Object.entries(CATEGORY_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <input placeholder={category === "L" ? "内网服务地址" : "API 端点"} value={endpoint} onChange={(e) => setEndpoint(e.target.value)} style={inputStyle} />
        <input placeholder="模型名称" value={modelName} onChange={(e) => setModelName(e.target.value)} style={inputStyle} />
        {category !== "L" && (
          <input placeholder={cfg.api_key_set ? "已设置（留空保持不变）" : "API Key"} type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} style={inputStyle} />
        )}
        <input type="number" step={0.1} placeholder="temperature" value={temperature} onChange={(e) => setTemperature(Number(e.target.value))} style={inputStyle} />
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 10, alignItems: "center" }}>
        <button
          onClick={() => onSave({ category, endpoint, model_name: modelName, temperature, ...(apiKey ? { api_key: apiKey } : {}) })}
          style={primaryBtnSmall}
        >
          保存
        </button>
        <button onClick={onTest} style={secondaryBtnSmall}>测试连接</button>
        {testResult && <span style={{ fontSize: 11, color: "#94a3b8" }}>{testResult}</span>}
      </div>
    </div>
  );
}

function FieldRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
      <div style={{ width: 140, fontSize: 12.5, color: "#374151", fontWeight: 600, flexShrink: 0 }}>{label}</div>
      {children}
    </div>
  );
}

function NumberField({ label, value, step, onSave }: { label: string; value: number; step?: number; onSave: (v: number) => void }) {
  return (
    <FieldRow label={label}>
      <input type="number" step={step ?? 1} defaultValue={value} onBlur={(e) => onSave(Number(e.target.value))} style={inputStyle} />
    </FieldRow>
  );
}

const sectionCard: CSSProperties = { background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20, marginBottom: 16 };
const sectionTitle: CSSProperties = { fontSize: 14, fontWeight: 800, margin: "0 0 12px" };
const inputStyle: CSSProperties = { border: "1px solid #d0d5dd", borderRadius: 6, padding: "7px 10px", fontSize: 12.5 };
const primaryBtnSmall: CSSProperties = { border: "none", background: "#2a78d6", color: "#fff", borderRadius: 6, padding: "6px 12px", fontSize: 12, cursor: "pointer" };
const secondaryBtnSmall: CSSProperties = { border: "1px solid #d0d5dd", background: "#fff", color: "#374151", borderRadius: 6, padding: "6px 12px", fontSize: 12, cursor: "pointer" };
