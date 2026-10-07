// 词汇表: the words and ontology entries accumulated from confirmed expert workflows and
// annotations (backend app/vocabulary.py). Read-only and append-only -- nothing here changes
// the records it came from; tidying records against it is a later step. Visible to 研究员
// (数据分析员) and 管理员 via DesktopApp's NAV gating; only 管理员 sees the one-off backfill.
import { Fragment, useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import { api } from "../api/client";
import type { Role, VocabularyEntry, VocabularyLayer, VocabularySummary } from "../api/types";
import { PillTabs, UnderlineTabs } from "../components/TabBar";

const LAYER_TABS: { key: VocabularyLayer; label: string }[] = [
  { key: "term", label: "词汇" },
  { key: "ontology", label: "本体条目" },
];

const LAYER_NOTES: Record<VocabularyLayer, string> = {
  term: "专家和标注人实际用过的说法，原样记录，不做同义词合并。同一个词在几条流程/标注里出现过，就记几次来源。",
  ontology: "从流程图整理出的结构化本体对象（角色、判断标准、时限、权限、异常、升级规则）。内容完全相同的对象算同一条。",
};

function fmtTime(iso: string): string {
  return iso ? iso.slice(0, 16).replace("T", " ") : "";
}

/** One-line summary of an ontology entry's content for the table (the label already names it). */
function contentHint(e: VocabularyEntry): string {
  const c = (e.content ?? {}) as Record<string, any>;
  if (e.kind === "checks") {
    const unit = c.unit ?? "";
    const normal = (c.limits ?? []).find((b: any) => b.band === "normal");
    const parts = [];
    if (normal) parts.push(`正常 ${normal.lower ?? ""}–${normal.upper ?? ""}${unit}`);
    if (c.expected?.target != null) parts.push(`目标 ${c.expected.target}${unit}`);
    return parts.join("，");
  }
  if (e.kind === "time_constraints") return [c.duration, c.on_violation?.action].filter(Boolean).join("，");
  if (e.kind === "escalation_policies")
    return (c.levels ?? []).map((l: any) => (l.to_role_id ?? "").replace(/^role_/, "")).filter(Boolean).join(" → ");
  return "";
}

export function VocabularyPage({ role }: { role: Role }) {
  const [layer, setLayer] = useState<VocabularyLayer>("term");
  const [summary, setSummary] = useState<VocabularySummary | null>(null);
  const [kind, setKind] = useState<string>("role");
  const [entries, setEntries] = useState<VocabularyEntry[]>([]);
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const s = await api.getVocabularySummary();
      setSummary(s);
      setEntries(await api.listVocabulary(layer, kind));
    } catch (e) {
      setError(String(e));
    }
  }, [layer, kind]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Switching layer resets the kind to that layer's first category.
  function switchLayer(next: VocabularyLayer) {
    setLayer(next);
    setKind(next === "term" ? "role" : "roles");
    setExpanded(null);
  }

  async function runBackfill() {
    setBusy(true);
    setNotice(null);
    try {
      const r = await api.backfillVocabulary(role);
      setNotice(`已从 ${r.workflows} 条已确认流程、${r.annotations} 条标注补录（重复补录不会重复计数）。`);
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const kindTabs = useMemo(
    () =>
      Object.entries(summary?.counts[layer] ?? {}).map(([key, v]) => ({ key, label: `${v.label} ${v.count}` })),
    [summary, layer],
  );
  const shown = entries.filter((e) => !query || e.label.includes(query) || e.steps.some((s) => s.includes(query)));

  return (
    <div style={{ height: "100%", overflowY: "auto", background: "#f6f7f9" }}>
      <div style={{ maxWidth: 960, margin: "0 auto", padding: "20px 24px 60px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h1 style={{ fontSize: 18, fontWeight: 800, margin: 0 }}>词汇表</h1>
          {role === "admin" && (
            <button onClick={runBackfill} disabled={busy} style={buttonStyle} title="把累积功能上线前已经确认的流程和已有标注也补进来">
              {busy ? "补录中…" : "从已有记录补录"}
            </button>
          )}
        </div>
        <div style={{ fontSize: 11.5, color: "#94a3b8", margin: "6px 0 14px" }}>
          专家确认提交流程、标注人采纳或修正流程时自动累积。只增不减，不会改动已有记录。
        </div>
        {error && <div style={{ fontSize: 12, color: "#b42318", marginBottom: 8 }}>{error}</div>}
        {notice && <div style={{ fontSize: 12, color: "#067647", marginBottom: 8 }}>{notice}</div>}

        <UnderlineTabs tabs={LAYER_TABS} active={layer} onChange={switchLayer} />
        <div style={{ fontSize: 11.5, color: "#667085", marginBottom: 10 }}>{LAYER_NOTES[layer]}</div>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
          {kindTabs.length > 0 && <PillTabs tabs={kindTabs} active={kind} onChange={(k) => { setKind(k); setExpanded(null); }} />}
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索词或步骤" style={inputStyle} />
        </div>

        <section style={sectionCard}>
          {shown.length === 0 ? (
            <div style={{ fontSize: 12, color: "#94a3b8" }}>还没有累积到这一类的内容。</div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
              <thead>
                <tr style={{ color: "#667085", textAlign: "left" }}>
                  <th style={th}>{layer === "term" ? "词" : "条目"}</th>
                  {layer === "ontology" && <th style={th}>内容</th>}
                  <th style={th}>出现的步骤</th>
                  <th style={{ ...th, textAlign: "right" }}>来源数</th>
                  <th style={th}>最近出现</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((e) => (
                  <Fragment key={e.key}>
                    <tr onClick={() => setExpanded(expanded === e.key ? null : e.key)} style={{ cursor: "pointer", borderTop: "1px solid #f2f4f7" }}>
                      <td style={td}>{e.label}</td>
                      {layer === "ontology" && <td style={{ ...td, color: "#475467" }}>{contentHint(e)}</td>}
                      <td style={{ ...td, color: "#475467" }}>{e.steps.slice(0, 3).join("、")}{e.steps.length > 3 ? ` 等 ${e.steps.length} 处` : ""}</td>
                      <td style={{ ...td, textAlign: "right" }}>{e.source_count}</td>
                      <td style={{ ...td, color: "#94a3b8" }}>{fmtTime(e.last_seen_at)}</td>
                    </tr>
                    {expanded === e.key && (
                      <tr>
                        <td colSpan={layer === "ontology" ? 5 : 4} style={{ ...td, background: "#f9fafb" }}>
                          <div style={{ color: "#667085", marginBottom: 4 }}>首次出现 {fmtTime(e.first_seen_at)}，来源：</div>
                          {e.sources.map((s) => (
                            <div key={`${s.type}:${s.id}`}>
                              {s.type === "expert_workflow" ? "专家录入" : "标注"} · {s.name || s.id} · {fmtTime(s.seen_at)}
                            </div>
                          ))}
                          {e.source_count > e.sources.length && <div style={{ color: "#94a3b8" }}>（另有 {e.source_count - e.sources.length} 个来源未列出）</div>}
                          {layer === "ontology" && e.content && (
                            <pre style={{ margin: "8px 0 0", fontSize: 11, whiteSpace: "pre-wrap", color: "#475467" }}>
                              {JSON.stringify(e.content, null, 2)}
                            </pre>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </div>
  );
}

const sectionCard: CSSProperties = { background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20, marginBottom: 16 };
const inputStyle: CSSProperties = { border: "1px solid #d0d5dd", borderRadius: 6, padding: "6px 10px", fontSize: 12.5, minWidth: 180 };
const buttonStyle: CSSProperties = { border: "1px solid #d0d5dd", background: "#fff", borderRadius: 6, padding: "6px 12px", fontSize: 12, cursor: "pointer" };
const th: CSSProperties = { padding: "6px 8px", fontWeight: 600, fontSize: 11.5 };
const td: CSSProperties = { padding: "7px 8px", verticalAlign: "top" };
