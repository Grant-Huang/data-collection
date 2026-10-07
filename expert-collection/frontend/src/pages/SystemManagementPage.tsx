// 系统管理: model config (level connections / per-slot references / reserved global model
// params), user & permissions (reserved -- no real account system yet), and system-level
// run params + the audit log. Split out from the old flat 系统设置 page so each concern has
// its own tab. Only reachable when role === "admin" (see DesktopApp's NAV minRole gating).
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { api } from "../api/client";
import { LLM_LEVEL_LABELS, LLM_SLOT_LABELS } from "../api/types";
import type { AuditLogEntry, LlmLevelConfig, LlmSlotConfig, Settings } from "../api/types";
import { PillTabs, UnderlineTabs } from "../components/TabBar";
import { TipIcon } from "../components/TipIcon";

const LEVEL_TIPS: Record<string, string> = {
  L: "本地部署的小模型：免费、响应快，但能力有限。适合「专家采集会话引导」这类高频、低风险的辅助任务。",
  C_standard: "云端 API 模型，标准档：能力强于 L，按量计费。适合 Error Analysis 归纳这类中等复杂度的任务。",
  C_flagship: "云端 API 模型，旗舰档：能力最强，成本也最高。适合实验结果解读这类对质量要求更高的任务。",
};

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
  dataset_rename: "数据集改名", dataset_delete: "数据集删除",
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
                    <FieldRow label="Workspace ID" tip="阿里云百炼的业务空间 ID（不是账号 ID），用来拼接语音服务的专属域名。格式类似 llm-sa1qz61xz9dg5dd3，在百炼控制台右上角用户菜单里能看到。">
                      <input
                        defaultValue={settings.voice.workspace_id}
                        onBlur={(e) => api.updateSettings({ voice: { workspace_id: e.target.value } }).then(setSettings)}
                        style={inputStyle}
                      />
                    </FieldRow>
                    <FieldRow label="Realtime 模型" tip="调用的语音识别/对话模型名称，例如 qwen3.5-omni-flash-realtime。不同模型的响应速度、能力和价格不同。">
                      <input
                        defaultValue={settings.voice.realtime_model}
                        onBlur={(e) => api.updateSettings({ voice: { realtime_model: e.target.value } }).then(setSettings)}
                        style={inputStyle}
                      />
                    </FieldRow>
                    <FieldRow label="API Key" tip="连接语音服务需要的密钥（跟大模型的 API Key 是两回事，两边都要各自配置）。已设置后这里不会回显明文，留空保存即代表不改动。">
                      <VoiceApiKeyField
                        keySet={settings.voice.api_key_set}
                        onSave={(apiKey) => api.updateSettings({ voice: { api_key: apiKey } }).then(setSettings)}
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
              <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 12 }}>
                这两项目前只是存起来，还没有接到实际的清理/超时逻辑上，属于预留参数——下面的审计日志表目前不会自动清理，移动端会话也没有自动过期。
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <NumberField
                  label="审计日志保留期限（天）"
                  value={settings.run_params.audit_log_retention_days}
                  tip="预留参数：按命名意图，本应是超过这个天数的审计日志会被清理。当前没有清理任务，日志会一直保留，改这里暂时不会影响任何行为。"
                  onSave={(v) => saveRunParams({ audit_log_retention_days: v })}
                />
                <NumberField
                  label="移动端会话超时（分钟，0=不限制）"
                  value={settings.run_params.mobile_session_timeout_minutes ?? 0}
                  tip="预留参数：按命名意图，本应是手机端会话闲置超过这个时长自动结束。当前没有会话过期逻辑，改这里暂时不会影响任何行为。"
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
  const isLocal = level === "L";
  // "L"'s endpoint is a local model's actual file path/internal address, masked by the
  // backend the same way an API key is (see settings.py's mask_for_display) -- never start
  // this field pre-filled with a real path, only send a new value if the admin typed one.
  const [endpoint, setEndpoint] = useState(isLocal ? "" : cfg.endpoint ?? "");
  const [modelName, setModelName] = useState(cfg.model_name ?? "");
  const [apiKey, setApiKey] = useState("");

  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 8, padding: 14 }}>
      <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8, display: "flex", alignItems: "center" }}>
        {LLM_LEVEL_LABELS[level] ?? level}
        {LEVEL_TIPS[level] && <TipIcon text={LEVEL_TIPS[level]} />}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <input
          placeholder={isLocal ? (cfg.endpoint_set ? "已设置（留空保持不变）" : "内网服务地址 / 模型文件路径") : "API 端点"}
          type={isLocal ? "password" : "text"}
          value={endpoint}
          onChange={(e) => setEndpoint(e.target.value)}
          style={inputStyle}
        />
        <input placeholder="模型名称" value={modelName} onChange={(e) => setModelName(e.target.value)} style={inputStyle} />
        {level !== "L" && (
          <input placeholder={cfg.api_key_set ? "已设置（留空保持不变）" : "API Key"} type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} style={inputStyle} />
        )}
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 10, alignItems: "center" }}>
        <button
          onClick={() => onSave({ ...(isLocal ? (endpoint ? { endpoint } : {}) : { endpoint }), model_name: modelName, ...(apiKey ? { api_key: apiKey } : {}) })}
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
      <span style={{ display: "flex", alignItems: "center", gap: 2 }}>
        <input type="number" step={0.1} value={temperature} onChange={(e) => setTemperature(Number(e.target.value))} style={{ ...inputStyle, width: 80 }} title="temperature" />
        <TipIcon text="Temperature（发散程度）：越接近 0 回答越严谨保守、可复现；越接近 1 回答越随机多样。0.0~0.2 适合需要精确结构化输出的任务，0.3 以上适合需要归纳/解读的文字生成任务。" />
      </span>
      <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11.5, color: "#374151" }}>
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        启用
      </label>
      <button onClick={() => onSave({ level, enabled, temperature })} style={primaryBtnSmall}>保存</button>
    </div>
  );
}

function VoiceApiKeyField({ keySet, onSave }: { keySet: boolean; onSave: (apiKey: string) => void }) {
  const [value, setValue] = useState("");
  return (
    <input
      type="password"
      placeholder={keySet ? "已设置（留空保持不变）" : "API Key"}
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => { if (value) { onSave(value); setValue(""); } }}
      style={inputStyle}
    />
  );
}

function FieldRow({ label, tip, children }: { label: string; tip?: string; children: ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
      <div style={{ width: 140, fontSize: 12.5, color: "#374151", fontWeight: 600, flexShrink: 0, display: "flex", alignItems: "center" }}>
        {label}
        {tip && <TipIcon text={tip} />}
      </div>
      {children}
    </div>
  );
}

function NumberField({ label, value, step, tip, onSave }: { label: string; value: number; step?: number; tip?: string; onSave: (v: number) => void }) {
  return (
    <FieldRow label={label} tip={tip}>
      <input type="number" step={step ?? 1} defaultValue={value} onBlur={(e) => onSave(Number(e.target.value))} style={inputStyle} />
    </FieldRow>
  );
}

const sectionCard: CSSProperties = { background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20, marginBottom: 16 };
const sectionTitle: CSSProperties = { fontSize: 14, fontWeight: 800, margin: "0 0 12px" };
const inputStyle: CSSProperties = { border: "1px solid #d0d5dd", borderRadius: 6, padding: "7px 10px", fontSize: 12.5 };
const primaryBtnSmall: CSSProperties = { border: "none", background: "#2a78d6", color: "#fff", borderRadius: 6, padding: "6px 12px", fontSize: 12, cursor: "pointer" };
const secondaryBtnSmall: CSSProperties = { border: "1px solid #d0d5dd", background: "#fff", color: "#374151", borderRadius: 6, padding: "6px 12px", fontSize: 12, cursor: "pointer" };
