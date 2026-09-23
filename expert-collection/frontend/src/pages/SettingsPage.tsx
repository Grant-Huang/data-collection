// PRD 17: real CRUD form. See app/settings.py's docstring / IMPLEMENTATION_PLAN.md
// assumption 6 -- saving a config here does not yet switch any Mock service's behavior
// (no reachable inference service in this sandbox); the quality/run params DO take effect.
//
// Model config is level-first (IMPLEMENTATION_PLAN.md section 11): configure each of the
// three levels once (endpoint/model/key), then every slot below just picks which level it
// uses. Previously each of the 8 slots carried its own full connection form, so the same
// endpoint had to be retyped into however many slots happened to share it.
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { api } from "../api/client";
import { LLM_LEVEL_LABELS, LLM_SLOT_LABELS, type LlmLevelConfig, type LlmSlotConfig, type Settings } from "../api/types";

export function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [testResults, setTestResults] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getSettings().then(setSettings).catch((e) => setError(String(e)));
  }, []);

  async function saveLlmLevel(level: string, patch: Partial<LlmLevelConfig> & { api_key?: string }) {
    if (!settings) return;
    setSaving(true);
    try {
      const updated = await api.updateSettings({ llm_levels: { [level]: patch } });
      setSettings(updated);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function saveLlmSlot(slot: string, patch: Partial<LlmSlotConfig>) {
    if (!settings) return;
    setSaving(true);
    try {
      const updated = await api.updateSettings({ llm_slots: { [slot]: patch } });
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

  async function handleTestConnection(level: string) {
    const res = await api.testConnection(level);
    setTestResults((prev) => ({ ...prev, [level]: res.message }));
  }

  if (!settings) return null;

  return (
    <div style={{ height: "100%", overflowY: "auto", background: "#f6f7f9" }}>
      <div style={{ maxWidth: 760, margin: "0 auto", padding: "20px 24px 60px" }}>
        <h1 style={{ fontSize: 18, fontWeight: 800, marginTop: 0 }}>系统设置</h1>
        {saving && <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 8 }}>保存中…</div>}

        <section style={sectionCard}>
          <h2 style={sectionTitle}>模型级别配置</h2>
          <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 12 }}>
            每个级别只配置一次（服务地址/模型名称/API Key），下面各环节直接引用级别，不用重复填连接信息。当前环境没有可达的推理服务，"测试连接"会如实反馈，不会伪造成功。
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {Object.entries(settings.llm_levels).map(([level, cfg]) => (
              <LlmLevelCard
                key={level}
                level={level}
                cfg={cfg}
                onSave={(patch) => saveLlmLevel(level, patch)}
                onTest={() => handleTestConnection(level)}
                testResult={testResults[level]}
              />
            ))}
          </div>
        </section>

        <section style={sectionCard}>
          <h2 style={sectionTitle}>环节引用级别（PRD 17.2）</h2>
          <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 12 }}>
            每个环节只需要选一个级别；temperature 是任务级别的调优参数，保留在这里单独配置，不随级别绑定。
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {Object.entries(settings.llm_slots).map(([slot, cfg]) => (
              <LlmSlotRow
                key={slot}
                slot={slot}
                cfg={cfg}
                levels={Object.keys(settings.llm_levels)}
                onSave={(patch) => saveLlmSlot(slot, patch)}
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

function LlmLevelCard({ level, cfg, onSave, onTest, testResult }: { level: string; cfg: LlmLevelConfig; onSave: (patch: Partial<LlmLevelConfig> & { api_key?: string }) => void; onTest: () => void; testResult?: string }) {
  const [endpoint, setEndpoint] = useState(cfg.endpoint ?? "");
  const [modelName, setModelName] = useState(cfg.model_name ?? "");
  const [apiKey, setApiKey] = useState("");

  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 8, padding: 14 }}>
      <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>{LLM_LEVEL_LABELS[level] ?? level}</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <input placeholder={level === "L" ? "内网服务地址" : "API 端点"} value={endpoint} onChange={(e) => setEndpoint(e.target.value)} style={inputStyle} />
        <input placeholder="模型名称" value={modelName} onChange={(e) => setModelName(e.target.value)} style={inputStyle} />
        {level !== "L" && (
          <input placeholder={cfg.api_key_set ? "已设置（留空保持不变）" : "API Key"} type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} style={inputStyle} />
        )}
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 10, alignItems: "center" }}>
        <button
          onClick={() => onSave({ endpoint, model_name: modelName, ...(apiKey ? { api_key: apiKey } : {}) })}
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

function LlmSlotRow({ slot, cfg, levels, onSave }: { slot: string; cfg: LlmSlotConfig; levels: string[]; onSave: (patch: Partial<LlmSlotConfig>) => void }) {
  const [level, setLevel] = useState(cfg.level);
  const [enabled, setEnabled] = useState(cfg.enabled ?? true);
  const [temperature, setTemperature] = useState(cfg.temperature ?? 0.2);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, border: "1px solid #e5e7eb", borderRadius: 8, padding: "10px 14px" }}>
      <div style={{ flex: 1, fontSize: 12.5, fontWeight: 600 }}>{LLM_SLOT_LABELS[slot] ?? slot}</div>
      <select value={level} onChange={(e) => setLevel(e.target.value)} style={{ ...inputStyle, width: 140 }}>
        {levels.map((l) => <option key={l} value={l}>{LLM_LEVEL_LABELS[l] ?? l}</option>)}
      </select>
      <input type="number" step={0.1} value={temperature} onChange={(e) => setTemperature(Number(e.target.value))} style={{ ...inputStyle, width: 80 }} title="temperature" />
      <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11.5, color: "#374151" }}>
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        启用
      </label>
      <button onClick={() => onSave({ level, enabled, temperature })} style={primaryBtnSmall}>保存</button>
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
