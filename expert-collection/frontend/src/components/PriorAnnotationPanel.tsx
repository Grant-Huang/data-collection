// Prior annotation modal -- design/case_context_and_prior_annotation_draft.md section 2,
// IMPLEMENTATION_PLAN.md section 9.2. Default interaction is "one click over the three big
// verdict buttons"; per-node review only appears when "需要修改" is picked (draft 2.2's
// "default only the coarsest grain, expand on demand" rule). "合并进上一个节点" is literally
// "merge into the previous node in this list" -- no free node-to-node picker, since the
// draft's own wording already fixes the target as the immediately preceding node.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { NodeVerdicts, PriorRecordDetail, PriorVerdict, Role } from "../api/types";
import { VERDICT_LABELS } from "../api/types";
import { DagView } from "./DagView";

const VERDICT_COLOR: Record<PriorVerdict, string> = {
  accepted: "#0ca30c", needs_revision: "#fab219", rejected: "#ec835a",
};

export function PriorAnnotationPanel({
  versionId, recordId, role, onClose, onSaved,
}: {
  versionId: string;
  recordId: string;
  role: Role;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [detail, setDetail] = useState<PriorRecordDetail | null>(null);
  const [verdict, setVerdict] = useState<PriorVerdict | null>(null);
  const [nodeVerdicts, setNodeVerdicts] = useState<NodeVerdicts>({});
  const [note, setNote] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.getPriorRecord(versionId, recordId).then((d) => {
      if (cancelled) return;
      setDetail(d);
      const latest = d.annotations[d.annotations.length - 1];
      setVerdict(latest?.verdict ?? null);
      setNodeVerdicts(latest?.node_verdicts ?? {});
      setNote(latest?.note ?? "");
      setExpanded((latest?.verdict ?? null) === "needs_revision");
    });
    return () => {
      cancelled = true;
    };
  }, [versionId, recordId]);

  function setNodeVerdict(nodeId: string, v: string) {
    setNodeVerdicts((prev) => ({ ...prev, [nodeId]: v }));
  }

  async function handleSave() {
    if (!verdict) return;
    setSaving(true);
    setError(null);
    try {
      await api.submitAnnotation(versionId, recordId, verdict, expanded ? nodeVerdicts : {}, note.trim() || null, role);
      onSaved();
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  if (!detail) return null;
  const nodes = detail.graph.nodes;

  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.35)", zIndex: 50 }} />
      <div
        style={{
          position: "fixed", top: "50%", left: "50%", transform: "translate(-50%, -50%)", zIndex: 51,
          width: 720, maxWidth: "92vw", maxHeight: "86vh", overflowY: "auto",
          background: "#fff", borderRadius: 12, padding: 24, boxShadow: "0 12px 40px rgba(0,0,0,0.25)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700 }}>{detail.name}</div>
            <div style={{ fontSize: 11.5, color: "#94a3b8", marginTop: 2 }}>
              {detail.prior_status === "expert_annotated" ? "已标注过，以下预选的是链上最新一次判定" : "尚未标注过"}
            </div>
          </div>
          <button onClick={onClose} style={{ border: "none", background: "none", fontSize: 18, cursor: "pointer" }}>
            ✕
          </button>
        </div>

        <div style={{ height: 260, border: "1px solid #e5e7eb", borderRadius: 8, marginBottom: 16 }}>
          <DagView graph={detail.graph} readOnly scrollable />
        </div>

        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          {(["accepted", "needs_revision", "rejected"] as PriorVerdict[]).map((v) => (
            <button
              key={v}
              onClick={() => {
                setVerdict(v);
                setExpanded(v === "needs_revision");
              }}
              style={{
                flex: 1, border: verdict === v ? "none" : "1px solid #d0d5dd",
                borderRadius: 8, padding: "10px 0", fontSize: 13, fontWeight: 600, cursor: "pointer",
                background: verdict === v ? VERDICT_COLOR[v] : "#fff",
                color: verdict === v ? "#fff" : "#475569",
              }}
            >
              {VERDICT_LABELS[v]}
            </button>
          ))}
        </div>

        {expanded && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "#667085", marginBottom: 8 }}>逐节点判定</div>
            {nodes.map((n, i) => {
              const prevId = i > 0 ? nodes[i - 1].node_id : null;
              const current = nodeVerdicts[n.node_id] ?? "keep";
              const options = prevId ? ["keep", "delete", `merge_into:${prevId}`] : ["keep", "delete"];
              return (
                <div key={n.node_id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0", borderBottom: "1px solid #f1f3f5" }}>
                  <div style={{ flex: 1, fontSize: 12.5 }}>{n.label}</div>
                  {options.map((opt) => (
                    <button
                      key={opt}
                      onClick={() => setNodeVerdict(n.node_id, opt)}
                      style={{
                        border: `1px solid ${current === opt ? "#2a78d6" : "#d0d5dd"}`,
                        color: current === opt ? "#2a78d6" : "#667085",
                        background: current === opt ? "#eef4fc" : "#fff",
                        borderRadius: 6, padding: "3px 10px", fontSize: 11.5, cursor: "pointer",
                      }}
                    >
                      {opt === "keep" ? "保留" : opt === "delete" ? "删除" : "合并进上一个节点"}
                    </button>
                  ))}
                </div>
              );
            })}
          </div>
        )}

        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="备注（可选）：为什么需要修改或丢弃"
          rows={2}
          style={{ width: "100%", boxSizing: "border-box", border: "1px solid #d0d5dd", borderRadius: 8, padding: "8px 10px", fontSize: 12.5, marginBottom: 12, fontFamily: "inherit" }}
        />

        {error && <div style={{ color: "#991b1b", fontSize: 12, marginBottom: 8 }}>{error}</div>}

        <button
          onClick={handleSave}
          disabled={!verdict || saving}
          style={{
            width: "100%", border: "none", borderRadius: 8, padding: "10px 0", fontWeight: 600, fontSize: 13,
            background: !verdict || saving ? "#e5e7eb" : "#0ca30c", color: !verdict || saving ? "#94a3b8" : "#fff",
            cursor: !verdict || saving ? "default" : "pointer",
          }}
        >
          {saving ? "保存中…" : "提交标注"}
        </button>

        {detail.annotations.length > 0 && (
          <div style={{ marginTop: 16, fontSize: 11.5, color: "#94a3b8" }}>
            标注历史（{detail.annotations.length} 次）：{detail.annotations.map((a) => VERDICT_LABELS[a.verdict]).join(" → ")}
          </div>
        )}
      </div>
    </>
  );
}
