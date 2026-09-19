// PRD 14: experiment list (default) -> create -> single result page (four layers, Dataset
// Slice omitted this round, see IMPLEMENTATION_PLAN.md section 7) -> comparison view.
import { useCallback, useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { api } from "../api/client";
import {
  IMPLEMENTED_METHODS,
  METHOD_LABELS,
  type DatasetVersionSummary,
  type ExperimentDetail,
  type ExperimentMethod,
  type ExperimentSummary,
} from "../api/types";
import type { Role } from "../api/types";
import { DagView } from "../components/DagView";

const STATUS_LABEL: Record<string, string> = { queued: "排队中", running: "运行中", completed: "已完成", failed: "失败" };
const STATUS_COLOR: Record<string, string> = { queued: "#94a3b8", running: "#2a78d6", completed: "#0ca30c", failed: "#d03b3b" };

type View = { kind: "list" } | { kind: "create" } | { kind: "detail"; id: string } | { kind: "compare"; ids: string[] };

export function ExperimentCenterPage({ role }: { role: Role }) {
  const [view, setView] = useState<View>({ kind: "list" });
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setExperiments(await api.listExperiments());
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (view.kind !== "list") return;
    const hasPending = experiments.some((e) => e.status === "queued" || e.status === "running");
    if (!hasPending) return;
    const timer = setInterval(refresh, 1500);
    return () => clearInterval(timer);
  }, [experiments, view.kind, refresh]);

  if (view.kind === "create") {
    return (
      <CreateExperimentForm
        role={role}
        onCreated={(id) => {
          refresh();
          setView({ kind: "detail", id });
        }}
        onCancel={() => setView({ kind: "list" })}
      />
    );
  }
  if (view.kind === "detail") {
    return <ExperimentDetailView id={view.id} onBack={() => setView({ kind: "list" })} />;
  }
  if (view.kind === "compare") {
    return <ComparisonView ids={view.ids} onBack={() => setView({ kind: "list" })} />;
  }

  return (
    <div style={{ height: "100%", overflowY: "auto", background: "#f6f7f9" }}>
      <div style={{ maxWidth: 980, margin: "0 auto", padding: "20px 24px 60px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h1 style={{ fontSize: 18, fontWeight: 800, margin: 0 }}>实验中心</h1>
          <div style={{ display: "flex", gap: 8 }}>
            {selected.size >= 2 && (
              <button
                onClick={() => setView({ kind: "compare", ids: [...selected] })}
                style={{ border: "1px solid #2a78d6", color: "#2a78d6", background: "#fff", borderRadius: 8, padding: "8px 14px", fontSize: 12.5, cursor: "pointer" }}
              >
                对比选中的 {selected.size} 个实验
              </button>
            )}
            <button
              onClick={() => setView({ kind: "create" })}
              style={{ border: "none", background: "#2a78d6", color: "#fff", borderRadius: 8, padding: "8px 14px", fontSize: 12.5, fontWeight: 600, cursor: "pointer" }}
            >
              + 新建实验
            </button>
          </div>
        </div>

        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
            <thead>
              <tr style={{ background: "#f8fafc", textAlign: "left" }}>
                <th style={thStyle}></th>
                <th style={thStyle}>名称</th>
                <th style={thStyle}>数据集</th>
                <th style={thStyle}>方法</th>
                <th style={thStyle}>状态</th>
                <th style={thStyle}>Node F1</th>
                <th style={thStyle}>Graph Structural F1</th>
                <th style={thStyle}>创建人</th>
                <th style={thStyle}>创建时间</th>
              </tr>
            </thead>
            <tbody>
              {experiments.map((exp) => (
                <tr key={exp.id} style={{ borderTop: "1px solid #f1f3f5" }}>
                  <td style={tdStyle}>
                    {exp.status === "completed" && (
                      <input
                        type="checkbox"
                        checked={selected.has(exp.id)}
                        onChange={(e) => {
                          const next = new Set(selected);
                          if (e.target.checked) next.add(exp.id);
                          else next.delete(exp.id);
                          setSelected(next);
                        }}
                      />
                    )}
                  </td>
                  <td style={{ ...tdStyle, cursor: "pointer", color: "#2a78d6", fontWeight: 600 }} onClick={() => setView({ kind: "detail", id: exp.id })}>
                    {exp.name}
                  </td>
                  <td style={tdStyle}>{exp.dataset_label}</td>
                  <td style={tdStyle}>{METHOD_LABELS[exp.method]}{exp.model_name ? `（${exp.model_name}）` : ""}</td>
                  <td style={tdStyle}>
                    <span style={{ color: STATUS_COLOR[exp.status], fontWeight: 600 }}>{STATUS_LABEL[exp.status]}</span>
                  </td>
                  <td style={tdStyle}>{exp.node_f1 ?? "—"}</td>
                  <td style={tdStyle}>{exp.graph_structural_f1 ?? "—"}</td>
                  <td style={tdStyle}>{exp.created_by}</td>
                  <td style={tdStyle}>{new Date(exp.created_at).toLocaleString("zh-CN")}</td>
                </tr>
              ))}
              {experiments.length === 0 && (
                <tr>
                  <td colSpan={9} style={{ ...tdStyle, textAlign: "center", color: "#94a3b8", padding: 32 }}>
                    还没有实验，点击右上角「+ 新建实验」开始
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {error && (
          <div style={{ marginTop: 16, background: "#fef2f2", border: "1px solid #fecaca", color: "#991b1b", borderRadius: 8, padding: "8px 12px", fontSize: 12 }}>
            {error}
          </div>
        )}
      </div>
    </div>
  );
}

const thStyle: CSSProperties = { padding: "10px 12px", fontWeight: 700, color: "#667085", fontSize: 11.5 };
const tdStyle: CSSProperties = { padding: "10px 12px", color: "#1f2937" };

function CreateExperimentForm({ role, onCreated, onCancel }: { role: Role; onCreated: (id: string) => void; onCancel: () => void }) {
  const [versions, setVersions] = useState<DatasetVersionSummary[]>([]);
  const [name, setName] = useState("");
  const [datasetVersionId, setDatasetVersionId] = useState("");
  const [method, setMethod] = useState<ExperimentMethod>("consensus_dfg");
  const [seed, setSeed] = useState(42);
  const [trainSplit, setTrainSplit] = useState(0.7);
  const [modelName, setModelName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listDatasetVersions("expert_collected").then((vs) => {
      setVersions(vs);
      if (vs[0]) setDatasetVersionId(vs[0].id);
    });
  }, []);

  async function handleSubmit() {
    if (!name.trim() || !datasetVersionId) {
      setError("请填写实验名称并选择数据集版本");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const exp = await api.createExperiment({
        name, source_type: "expert_collected", dataset_version_id: datasetVersionId,
        input_version: "raw", representation: "node_edge_graph", method,
        model_name: method === "llm_extractor" ? modelName : null,
        seed, train_split: trainSplit,
        gold_nodes: false, gold_edges: false, gold_boundary: false, gold_roles: false,
        actor_role: role,
      });
      onCreated(exp.id);
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{ height: "100%", overflowY: "auto", background: "#f6f7f9" }}>
      <div style={{ maxWidth: 560, margin: "0 auto", padding: "20px 24px 60px" }}>
        <button onClick={onCancel} style={{ border: "none", background: "none", color: "#667085", fontSize: 12.5, cursor: "pointer", padding: 0, marginBottom: 12 }}>
          ← 返回实验列表
        </button>
        <h1 style={{ fontSize: 18, fontWeight: 800, marginTop: 0 }}>新建实验</h1>

        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20, display: "flex", flexDirection: "column", gap: 14 }}>
          <Field label="实验名称">
            <input value={name} onChange={(e) => setName(e.target.value)} style={inputStyle} placeholder="例如：consensus baseline v1" />
          </Field>
          <Field label="数据源">
            <input disabled value="Expert（专家采集）" style={{ ...inputStyle, color: "#94a3b8" }} />
          </Field>
          <Field label="数据集版本">
            <select value={datasetVersionId} onChange={(e) => setDatasetVersionId(e.target.value)} style={inputStyle}>
              {versions.map((v) => (
                <option key={v.id} value={v.id}>v{v.version_number}（{v.workflow_count} 条工作流）</option>
              ))}
            </select>
            {versions.length === 0 && <div style={{ fontSize: 11.5, color: "#94a3b8", marginTop: 4 }}>还没有已发布的数据集版本，请先在 Dashboard 发布一个。</div>}
          </Field>
          <Field label="表示方式">
            <input disabled value="Node-Edge Graph" style={{ ...inputStyle, color: "#94a3b8" }} />
          </Field>
          <Field label="方法（Method）">
            <select value={method} onChange={(e) => setMethod(e.target.value as ExperimentMethod)} style={inputStyle}>
              {Object.entries(METHOD_LABELS).map(([key, label]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </select>
            {!IMPLEMENTED_METHODS.includes(method) && (
              <div style={{ fontSize: 11.5, color: "#b45309", marginTop: 4 }}>该方法本轮未接入真实执行引擎，提交后会诚实标记为失败，不会产出假指标。</div>
            )}
          </Field>
          {method === "llm_extractor" && (
            <Field label="模型（Model）">
              <input value={modelName} onChange={(e) => setModelName(e.target.value)} style={inputStyle} placeholder="例如：qwen3.5-plus" />
            </Field>
          )}
          <Field label="Seed">
            <input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} style={inputStyle} />
          </Field>
          <Field label={`Train Split（${Math.round(trainSplit * 100)}% / ${Math.round((1 - trainSplit) * 100)}%）`}>
            <input type="range" min={0.5} max={0.9} step={0.05} value={trainSplit} onChange={(e) => setTrainSplit(Number(e.target.value))} />
          </Field>

          <button
            onClick={handleSubmit}
            disabled={submitting}
            style={{ border: "none", background: "#2a78d6", color: "#fff", borderRadius: 8, padding: "10px 0", fontWeight: 600, cursor: "pointer", marginTop: 8 }}
          >
            {submitting ? "提交中…" : "Run"}
          </button>
          {error && <div style={{ color: "#991b1b", fontSize: 12 }}>{error}</div>}
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12.5, color: "#374151", fontWeight: 600 }}>
      {label}
      {children}
    </label>
  );
}

const inputStyle: CSSProperties = { border: "1px solid #d0d5dd", borderRadius: 6, padding: "8px 10px", fontSize: 13, fontWeight: 400 };

function ExperimentDetailView({ id, onBack }: { id: string; onBack: () => void }) {
  const [exp, setExp] = useState<ExperimentDetail | null>(null);
  const [editing, setEditing] = useState(false);
  const [draftText, setDraftText] = useState("");

  const refresh = useCallback(() => {
    api.getExperiment(id).then(setExp);
  }, [id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!exp || exp.status === "completed" || exp.status === "failed") return;
    const timer = setInterval(refresh, 1000);
    return () => clearInterval(timer);
  }, [exp, refresh]);

  if (!exp) return null;

  return (
    <div style={{ height: "100%", overflowY: "auto", background: "#f6f7f9" }}>
      <div style={{ maxWidth: 900, margin: "0 auto", padding: "20px 24px 60px" }}>
        <button onClick={onBack} style={{ border: "none", background: "none", color: "#667085", fontSize: 12.5, cursor: "pointer", padding: 0, marginBottom: 12 }}>
          ← 返回实验列表
        </button>
        <h1 style={{ fontSize: 18, fontWeight: 800, marginTop: 0 }}>{exp.name}</h1>
        <div style={{ fontSize: 12, color: "#667085", marginBottom: 16, lineHeight: 1.8 }}>
          数据集：{exp.dataset_label} · 表示方式：{exp.representation} · 方法：{METHOD_LABELS[exp.method]}
          {exp.model_name && ` (${exp.model_name})`} · Prompt 版本：{exp.prompt_version ?? "—"} · Seed：{exp.seed} · 状态：
          <span style={{ color: STATUS_COLOR[exp.status], fontWeight: 700 }}> {STATUS_LABEL[exp.status]}</span>
        </div>

        {exp.status === "failed" && (
          <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 10, padding: 16, color: "#991b1b", fontSize: 13, marginBottom: 16 }}>
            实验失败：{exp.failure_reason}
          </div>
        )}
        {(exp.status === "queued" || exp.status === "running") && (
          <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 24, textAlign: "center", color: "#667085", fontSize: 13 }}>
            {STATUS_LABEL[exp.status]}…
          </div>
        )}

        {exp.status === "completed" && (
          <>
            <section style={sectionCard}>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>结果解读</div>
              {editing ? (
                <>
                  <textarea value={draftText} onChange={(e) => setDraftText(e.target.value)} rows={8} style={{ width: "100%", fontSize: 12.5, padding: 10, border: "1px solid #d0d5dd", borderRadius: 6, fontFamily: "inherit" }} />
                  <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                    <button onClick={async () => { await api.updateExplanation(exp.id, draftText); setEditing(false); refresh(); }} style={primaryBtnSmall}>保存</button>
                    <button onClick={() => setEditing(false)} style={secondaryBtnSmall}>取消</button>
                  </div>
                </>
              ) : (
                <>
                  <div style={{ fontSize: 12.5, color: "#1f2937", lineHeight: 1.8, whiteSpace: "pre-wrap" }}>{exp.explanation}</div>
                  <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                    <button onClick={() => { setDraftText(exp.explanation ?? ""); setEditing(true); }} style={secondaryBtnSmall}>编辑</button>
                    <button onClick={async () => { await api.regenerateExplanation(exp.id); refresh(); }} style={secondaryBtnSmall}>重新生成</button>
                    {exp.explanation_edited && <span style={{ fontSize: 11, color: "#b45309", alignSelf: "center" }}>已人工修订</span>}
                  </div>
                </>
              )}
            </section>

            <section style={sectionCard}>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>Summary</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))", gap: 10 }}>
                <MetricTile label="Node F1" value={exp.metrics.node_f1} />
                <MetricTile label="Edge F1" value={exp.metrics.edge_f1} />
                <MetricTile label="Graph Structural F1" value={exp.metrics.graph_structural_f1} />
                <MetricTile label="结构特征匹配率" value={exp.metrics.structural_match_rate} />
                <MetricTile label="Train / Test" value={`${exp.train_count} / ${exp.test_count}`} isText />
              </div>
            </section>

            <section style={sectionCard}>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>Graph（挖出来的共识结构）</div>
              <div style={{ height: 320, border: "1px solid #f1f3f5", borderRadius: 8 }}>
                {exp.consensus_graph && <DagView graph={exp.consensus_graph} readOnly />}
              </div>
            </section>

            <section style={sectionCard}>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>Error Analysis（匹配度较低的测试样本）</div>
              {exp.error_analysis.length === 0 ? (
                <div style={{ fontSize: 12.5, color: "#94a3b8" }}>测试集所有工作流都匹配良好，没有需要关注的样本。</div>
              ) : (
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
                  <thead>
                    <tr style={{ textAlign: "left", color: "#667085" }}>
                      <th style={thStyle}>工作流</th><th style={thStyle}>结构类型</th><th style={thStyle}>Node F1</th><th style={thStyle}>Edge F1</th>
                    </tr>
                  </thead>
                  <tbody>
                    {exp.error_analysis.map((c, i) => (
                      <tr key={i} style={{ borderTop: "1px solid #f1f3f5" }}>
                        <td style={tdStyle}>{c.workflow_name}</td><td style={tdStyle}>{c.group}</td>
                        <td style={tdStyle}>{c.node_f1}</td><td style={tdStyle}>{c.edge_f1}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>

            <section style={{ ...sectionCard, color: "#94a3b8", fontSize: 12.5 }}>
              Dataset Slice（按行业/制造模式/场景切片）本轮未实现——需要本系统尚未采集的分类字段，与 Dashboard 覆盖度维度是同一个缺口。
            </section>
          </>
        )}
      </div>
    </div>
  );
}

function MetricTile({ label, value, isText }: { label: string; value: number | string | undefined; isText?: boolean }) {
  return (
    <div style={{ background: "#f8fafc", borderRadius: 8, padding: "10px 12px" }}>
      <div style={{ fontSize: 11, color: "#667085" }}>{label}</div>
      <div style={{ fontSize: isText ? 15 : 20, fontWeight: 800, color: "#1f2937" }}>{value ?? "—"}</div>
    </div>
  );
}

function ComparisonView({ ids, onBack }: { ids: string[]; onBack: () => void }) {
  const [result, setResult] = useState<Awaited<ReturnType<typeof api.compareExperiments>> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.compareExperiments(ids).then(setResult).catch((e) => setError(String(e)));
  }, [ids]);

  if (error) return <div style={{ padding: 24, color: "#991b1b" }}>{error}</div>;
  if (!result) return null;

  const colors = ["#2a78d6", "#f59e0b", "#8b5cf6", "#10b981", "#ec835a"];

  return (
    <div style={{ height: "100%", overflowY: "auto", background: "#f6f7f9" }}>
      <div style={{ maxWidth: 900, margin: "0 auto", padding: "20px 24px 60px" }}>
        <button onClick={onBack} style={{ border: "none", background: "none", color: "#667085", fontSize: 12.5, cursor: "pointer", padding: 0, marginBottom: 12 }}>
          ← 返回实验列表
        </button>
        <h1 style={{ fontSize: 18, fontWeight: 800, marginTop: 0 }}>实验对比</h1>

        <section style={sectionCard}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>指标对比表</div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
            <thead>
              <tr style={{ textAlign: "left" }}>
                <th style={thStyle}>指标</th>
                {result.experiments.map((e) => <th key={e.id} style={thStyle}>{e.name}</th>)}
              </tr>
            </thead>
            <tbody>
              {result.metric_table.rows.map((row) => (
                <tr key={row.key} style={{ borderTop: "1px solid #f1f3f5" }}>
                  <td style={tdStyle}>{row.label}</td>
                  {row.values.map((v, i) => (
                    <td key={i} style={{ ...tdStyle, fontWeight: v === row.best_value ? 800 : 400, color: v === row.best_value ? "#0ca30c" : "#1f2937" }}>
                      {v ?? "—"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section style={sectionCard}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>核心指标对比</div>
          {["node_f1", "edge_f1"].map((key) => (
            <div key={key} style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 11.5, color: "#667085", marginBottom: 6 }}>{key === "node_f1" ? "Node F1" : "Edge F1"}</div>
              <div style={{ display: "flex", gap: 8, alignItems: "flex-end", height: 80 }}>
                {result.experiments.map((e, i) => {
                  const val = (e as unknown as Record<string, number>)[key] ?? 0;
                  return (
                    <div key={e.id} style={{ display: "flex", flexDirection: "column", alignItems: "center", flex: 1 }}>
                      <div style={{ fontSize: 11, marginBottom: 4 }}>{val}</div>
                      <div style={{ width: "100%", height: Math.max(4, val * 60), background: colors[i % colors.length], borderRadius: "4px 4px 0 0" }} />
                    </div>
                  );
                })}
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                {result.experiments.map((e, i) => (
                  <div key={e.id} style={{ flex: 1, fontSize: 10.5, textAlign: "center", color: colors[i % colors.length] }}>{e.name}</div>
                ))}
              </div>
            </div>
          ))}
        </section>

        <section style={sectionCard}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>对比解读</div>
          <div style={{ fontSize: 12.5, color: "#1f2937", lineHeight: 1.8, whiteSpace: "pre-wrap" }}>{result.narrative}</div>
        </section>
      </div>
    </div>
  );
}

const sectionCard: CSSProperties = { background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20, marginBottom: 16 };
const primaryBtnSmall: CSSProperties = { border: "none", background: "#2a78d6", color: "#fff", borderRadius: 6, padding: "6px 12px", fontSize: 12, cursor: "pointer" };
const secondaryBtnSmall: CSSProperties = { border: "1px solid #d0d5dd", background: "#fff", color: "#374151", borderRadius: 6, padding: "6px 12px", fontSize: 12, cursor: "pointer" };
