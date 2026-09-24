// Rework step (IMPLEMENTATION_PLAN.md section 16, decision 9): a round settled on "需要修改",
// so someone turns the annotators' suggestions into an actual corrected graph. The reworker
// starts from one annotator's node verdicts (or the arbitrator's), adjusts on the graph
// (delete / merge into a real predecessor / rename / insert a missing step), watches a live
// server-side preview -- the same apply + validate code path the submission uses -- and
// submits. The corrected graph then goes back into blind double review as the next round.
import { useEffect, useMemo, useState } from "react";
import { api, apiErrorMessage } from "../../api/client";
import type { Graph, PriorRecordDetail, ReworkEdits, Role, ValidationIssue } from "../../api/types";
import { DagView, type NodeDecoration } from "../DagView";
import { describeVerdict, verdictDecorations } from "../../utils/annotationAccess";
import { AnnotationCard } from "./AnnotationCards";
import { NodeActionBar } from "./NodeActionBar";

const EMPTY: ReworkEdits = { node_verdicts: {}, renames: {}, inserts: [] };

function hasChanges(e: ReworkEdits): boolean {
  return Object.values(e.node_verdicts).some((v) => v !== "keep") || Object.keys(e.renames).length > 0 || e.inserts.length > 0;
}

export function ReworkEditor({
  versionId, detail, reworkerName, role, onSubmitted,
}: {
  versionId: string;
  detail: PriorRecordDetail;
  reworkerName: string;
  role: Role;
  onSubmitted: () => void;
}) {
  const graph = detail.graph;
  const suggestions = detail.annotations.filter((a) => (a.round ?? 1) === detail.round && a.verdict === "needs_revision");
  const arbitration = suggestions.find((a) => a.role_in_process === "arbitration");

  // Start from the arbitrator's suggestion when there is one (it's the deciding judgement);
  // otherwise from the two independents' suggestion if they happen to be identical; otherwise
  // empty, and the reworker picks which suggestion to start from.
  const initial = useMemo<ReworkEdits>(() => {
    if (arbitration) return { ...EMPTY, node_verdicts: { ...arbitration.node_verdicts } };
    const [a, b] = suggestions;
    if (a && b && JSON.stringify(a.node_verdicts) === JSON.stringify(b.node_verdicts)) {
      return { ...EMPTY, node_verdicts: { ...a.node_verdicts } };
    }
    return EMPTY;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail.record_id, detail.round]);

  const [edits, setEdits] = useState<ReworkEdits>(initial);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ graph: Graph; issues: ValidationIssue[] } | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setEdits(initial);
    setSelectedId(null);
    setNote("");
    setError(null);
  }, [initial]);

  // Live preview, debounced so typing a rename doesn't fire a request per keystroke.
  useEffect(() => {
    if (!hasChanges(edits)) {
      setPreview(null);
      setPreviewError(null);
      return;
    }
    let cancelled = false;
    const t = setTimeout(() => {
      api.previewRework(versionId, detail.record_id, edits)
        .then((p) => {
          if (cancelled) return;
          setPreview(p);
          setPreviewError(null);
        })
        .catch((e) => {
          if (cancelled) return;
          setPreview(null);
          setPreviewError(apiErrorMessage(e));
        });
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [edits, versionId, detail.record_id]);

  const selected = graph.nodes.find((n) => n.node_id === selectedId) ?? null;
  const decorations = useMemo(() => {
    const d: Record<string, NodeDecoration> = verdictDecorations(edits.node_verdicts, selectedId);
    for (const id of Object.keys(edits.renames)) d[id] = { ...(d[id] ?? {}), badge: d[id]?.badge ?? "改名", badgeColor: d[id]?.badgeColor ?? "#0f766e" };
    for (const ins of edits.inserts) {
      d[ins.after] = { ...(d[ins.after] ?? {}), badge: `${d[ins.after]?.badge ? d[ins.after]?.badge + "・" : ""}后插入`, badgeColor: d[ins.after]?.badgeColor ?? "#0f766e" };
    }
    return d;
  }, [edits, selectedId]);

  const errors = preview?.issues.filter((i) => i.level === "error") ?? [];
  const canSubmit = hasChanges(edits) && !!preview && errors.length === 0 && !previewError && !!reworkerName.trim() && !saving;

  async function submit() {
    if (!canSubmit) return;
    setSaving(true);
    setError(null);
    try {
      await api.submitRework(versionId, detail.record_id, {
        edits, reworker_name: reworkerName.trim(), note: note.trim() || null, actor_role: role, round: detail.round,
      });
      onSubmitted();
    } catch (e) {
      setError(apiErrorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  const editItems: { key: string; text: string; remove: () => void }[] = [
    ...Object.entries(edits.node_verdicts).filter(([, v]) => v !== "keep").map(([id, v]) => ({
      key: `v-${id}`,
      text: `「${graph.nodes.find((n) => n.node_id === id)?.label ?? id}」${describeVerdict(graph, v)}`,
      remove: () => setEdits((e) => {
        const nv = { ...e.node_verdicts };
        delete nv[id];
        return { ...e, node_verdicts: nv };
      }),
    })),
    ...Object.entries(edits.renames).map(([id, label]) => ({
      key: `r-${id}`,
      text: `「${graph.nodes.find((n) => n.node_id === id)?.label ?? id}」改名为「${label}」`,
      remove: () => setEdits((e) => {
        const rn = { ...e.renames };
        delete rn[id];
        return { ...e, renames: rn };
      }),
    })),
    ...edits.inserts.map((ins, i) => ({
      key: `i-${i}`,
      text: `在「${graph.nodes.find((n) => n.node_id === ins.after)?.label ?? ins.after}」之后插入「${ins.label}」`,
      remove: () => setEdits((e) => ({ ...e, inserts: e.inserts.filter((_, j) => j !== i) })),
    })),
  ];

  return (
    <div>
      <div style={{ fontSize: 12, fontWeight: 700, color: "#667085", marginBottom: 6 }}>
        本轮修改建议（{suggestions.length} 份）——点"以此为起点"载入它的节点判定，再在图上调整
      </div>
      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        {suggestions.map((a) => (
          <AnnotationCard
            key={a.annotation_id}
            a={a}
            graph={graph}
            footer={
              <button
                onClick={() => {
                  setEdits({ ...EMPTY, node_verdicts: { ...a.node_verdicts } });
                  setSelectedId(null);
                }}
                style={{ marginTop: 6, border: "1px solid #2a78d6", color: "#2a78d6", background: "#fff", borderRadius: 6, padding: "3px 10px", fontSize: 11.5, cursor: "pointer" }}
              >
                以此为起点
              </button>
            }
          />
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 4 }}>当前图（点节点进行修改）</div>
          <div style={{ maxHeight: 440, overflowY: "auto", border: "1px solid #e5e7eb", borderRadius: 8 }}>
            <DagView graph={graph} readOnly scrollable nodeDecorations={decorations} onNodeTap={(n) => setSelectedId(n.node_id)} />
          </div>
        </div>
        <div>
          <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 4 }}>修正后预览</div>
          <div style={{ maxHeight: 440, minHeight: 200, overflowY: "auto", border: "1px solid #e5e7eb", borderRadius: 8, background: preview ? "#fff" : "#f8fafc" }}>
            {preview ? (
              <DagView graph={preview.graph} readOnly scrollable />
            ) : (
              <div style={{ display: "flex", height: 200, alignItems: "center", justifyContent: "center", fontSize: 12, color: "#94a3b8", padding: 16, textAlign: "center" }}>
                {previewError ?? "还没有修改。先选一份建议作为起点，或直接在左侧图上点节点修改。"}
              </div>
            )}
          </div>
        </div>
      </div>

      {selected && (
        <NodeActionBar
          graph={graph}
          node={selected}
          verdict={edits.node_verdicts[selected.node_id]}
          onVerdict={(v) => setEdits((e) => {
            const nv = { ...e.node_verdicts };
            if (v === "keep") delete nv[selected.node_id];
            else nv[selected.node_id] = v;
            const rn = { ...e.renames };
            if (v !== "keep") delete rn[selected.node_id]; // a deleted/merged node can't also be renamed
            return { ...e, node_verdicts: nv, renames: rn };
          })}
          rework={{
            rename: edits.renames[selected.node_id],
            onRename: (label) => setEdits((e) => {
              const rn = { ...e.renames };
              if (label) rn[selected.node_id] = label;
              else delete rn[selected.node_id];
              return { ...e, renames: rn };
            }),
            onInsertAfter: (label) => setEdits((e) => ({ ...e, inserts: [...e.inserts, { after: selected.node_id, label }] })),
          }}
          onClose={() => setSelectedId(null)}
        />
      )}

      {editItems.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "#667085", marginBottom: 4 }}>已做的修改（{editItems.length}）</div>
          {editItems.map((it) => (
            <div key={it.key} style={{ display: "flex", justifyContent: "space-between", fontSize: 12, padding: "3px 0", borderBottom: "1px solid #f1f3f5" }}>
              <span>{it.text}</span>
              <button onClick={it.remove} style={{ border: "none", background: "none", color: "#94a3b8", cursor: "pointer" }}>撤销</button>
            </div>
          ))}
        </div>
      )}

      {preview && preview.issues.length > 0 && (
        <div style={{ fontSize: 12, marginBottom: 10 }}>
          {preview.issues.map((i, k) => (
            <div key={k} style={{ color: i.level === "error" ? "#991b1b" : "#92400e" }}>
              {i.level === "error" ? "✖" : "⚠"} {i.message}
            </div>
          ))}
        </div>
      )}

      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="返工说明（可选）：改了什么、为什么"
        rows={2}
        style={{ width: "100%", boxSizing: "border-box", border: "1px solid #d0d5dd", borderRadius: 8, padding: "8px 10px", fontSize: 12.5, marginBottom: 8, fontFamily: "inherit" }}
      />
      {error && <div style={{ color: "#991b1b", fontSize: 12, marginBottom: 8 }}>{error}</div>}
      <button
        onClick={submit}
        disabled={!canSubmit}
        style={{
          width: "100%", border: "none", borderRadius: 8, padding: "10px 0", fontWeight: 600, fontSize: 13,
          background: canSubmit ? "#2a78d6" : "#e5e7eb", color: canSubmit ? "#fff" : "#94a3b8",
          cursor: canSubmit ? "pointer" : "default",
        }}
      >
        {saving ? "提交中…" : !reworkerName.trim() ? "请先在上方填写你的姓名" : errors.length > 0 ? "修正后的图结构不合法，请先处理上面的错误" : "提交返工（修正后的图将进入下一轮双人独立标注）"}
      </button>
    </div>
  );
}
