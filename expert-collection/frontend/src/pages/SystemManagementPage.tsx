// 系统管理: model config (level connections / per-slot references / reserved global model
// params), user & permissions (reserved -- no real account system yet), and system-level
// run params + the audit log. Split out from the old flat 系统设置 page so each concern has
// its own tab. Only reachable when role === "admin" (see DesktopApp's NAV minRole gating).
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { api } from "../api/client";
import { LLM_LEVEL_LABELS, LLM_SLOT_LABELS } from "../api/types";
import type { AuditLogEntry, LlmLevelConfig, LlmSlotConfig, Settings } from "../api/types";
import { PillTabs, UnderlineTabs } from "../components/TabBar";

type MainTab = "model" | "permissions" | "system";
type ModelSubTab = "config" | "reference" | "params";

const MAIN_TABS: { key: MainTab; label: string }[] = [
  { key: "model", label: "模型设置" },
  { key: "permissions", label: "用户与权限" },
  { key: "system", label: "系统设置" },
];

const MODEL_SUB_TABS: { key: ModelSubTab; label: string }[] = [
  { key: "config", label: "模型配置" },
  { key: "reference", label: "模型引用" },
  { key: "params", label: "模型参数" },
];

const ACTION_LABELS: Record<string, string> = {
  dataset_publish: "数据集发布", dataset_archive: "数据集归档", dataset_import: "数据集导入",
  dataset_mark_gold: "标记 Gold 版本", dataset_unmark_gold: "取消 Gold 标记", experiment_create: "创建实验",
};

export function SystemManagementPage() {
  const [mainTab, setMainTab] = useState<MainTab>("model");
  const [modelSubTab, setModelSubTab] = useState<ModelSubTab>("config");
  const [settings, setSettings] = useState<Settings | null>(null);
  const [testResults, setTestResults] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getSettings().then(setSettings).catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (mainTab === "system") api.getAuditLog().then(setEntries).catch((e) => setError(String(e)));
  }, [mainTab]);

  async function saveLlmLevel(level: string, patch: Partial<LlmLevelConfig> & { api_key?: string }) {
    if (!settings) return;
    setSaving(true);
    try {
      setSettings(await api.updateSettings({ llm_levels: { [level]: patch } }));
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
      setSettings(await api.updateSettings({ llm_slots: { [slot]: patch } }));
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

  return (
    <div style={{ height: "100%", overflowY: "auto", background: "#f6f7f9" }}>
      <div style={{ maxWidth: 760, margin: "0 auto", padding: "20px 24px 60px" }}>
        <h1 style={{ fontSize: 18, fontWeight: 800, marginTop: 0 }}>系统管理</h1>
        {saving && <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 8 }}>保存中…</div>}

        <UnderlineTabs tabs={MAIN_TABS} active={mainTab} onChange={setMainTab} />

        {mainTab === "model" && settings && (
          <>
            <div style={{ marginBottom: 16 }}>
              <PillTabs tabs={MODEL_SUB_TABS} active={modelSubTab} onChange={setModelSubTab} />
            </div>

            {modelSubTab === "config" && (
              <>
                <section style={sectionCard}>
                  <h2 style={sectionTitle}>模型级别配置（大模型）</h2>
                  <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 12 }}>
                    每个级别只配置一次（服务地址/模型名称/API Key），「模型引用」子 Tab 里各环节直接引用级别，不用重复填连接信息。当前环境没有可达的推理服务，"测试连接"会如实反馈，不会伪造成功。
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
                  <h2 style={sectionTitle}>语音识别配置</h2>
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
              </>
            )}

            {modelSubTab === "reference" && (
              <section style={sectionCard}>
                <h2 style={sectionTitle}>环节引用级别</h2>
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
            )}

            {modelSubTab === "params" && (
              <section style={sectionCard}>
                <h2 style={sectionTitle}>模型参数</h2>
                <div style={{ fontSize: 12.5, color: "#94a3b8" }}>
                  预留——目前没有跨级别/跨环节的全局模型参数需要配置（各环节自己的 temperature 在「模型引用」子 Tab 里）。
                </div>
              </section>
            )}
          </>
        )}

        {mainTab === "permissions" && (
          <section style={sectionCard}>
            <h2 style={sectionTitle}>用户与权限</h2>
            <div style={{ fontSize: 12.5, color: "#94a3b8" }}>
              预留——当前没有真实账号体系，做一个假的用户/角色管理页面没有意义（IMPLEMENTATION_PLAN.md 第 7 节）。现在的"身份"只是顶部导航里的一个本地角色切换器（专家/研究员/管理员），用于演示各角色可见的功能范围，不是真实登录。
            </div>
          </section>
        )}

        {mainTab === "system" && settings && (
          <>
            <section style={sectionCard}>
              <h2 style={sectionTitle}>系统运行参数</h2>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <NumberField
                  label="审计日志保留期限（天）"
                  value={settings.run_params.audit_log_retention_days}
                  onSave={(v) => saveRunParams({ audit_log_retention_days: v })}
                />
                <NumberField
                  label="移动端会话超时（分钟，0=不限制）"
                  value={settings.run_params.mobile_session_timeout_minutes ?? 0}
                  onSave={(v) => saveRunParams({ mobile_session_timeout_minutes: v || null })}
                />
              </div>
            </section>

            <section style={sectionCard}>
              <h2 style={sectionTitle}>审计日志</h2>
              <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 12 }}>
                没有真实多用户登录，"谁"只能记到当前选择的身份，不是真实账号；只记录数据集发布/归档/导入、Gold 标记、实验创建这些真正在发生的操作。
              </div>
              <table style={{ width: "100%", tableLayout: "fixed", borderCollapse: "collapse", fontSize: 12.5 }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "#667085" }}>
                    <th style={{ padding: "8px 10px", width: 100 }}>操作</th>
                    <th style={{ padding: "8px 10px", width: 70 }}>身份</th>
                    <th style={{ padding: "8px 10px" }}>详情</th>
                    <th style={{ padding: "8px 10px", width: 130 }}>时间</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((e) => (
                    <tr key={e.id} style={{ borderTop: "1px solid #f1f3f5" }}>
                      <td style={{ padding: "8px 10px", fontWeight: 600 }}>{ACTION_LABELS[e.action] ?? e.action}</td>
                      <td style={{ padding: "8px 10px" }}>{e.actor_role}</td>
                      <td style={{ padding: "8px 10px", color: "#667085", wordBreak: "break-all", whiteSpace: "normal" }}>
                        {JSON.stringify(e.detail)}
                      </td>
                      <td style={{ padding: "8px 10px", color: "#667085" }}>{new Date(e.created_at).toLocaleString("zh-CN")}</td>
                    </tr>
                  ))}
                  {entries.length === 0 && (
                    <tr><td colSpan={4} style={{ padding: 24, textAlign: "center", color: "#94a3b8" }}>还没有记录</td></tr>
                  )}
                </tbody>
              </table>
            </section>
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
