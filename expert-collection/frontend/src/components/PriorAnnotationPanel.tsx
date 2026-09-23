// Prior annotation modal -- design/case_context_and_prior_annotation_draft.md section 2,
// IMPLEMENTATION_PLAN.md section 9.2. Default interaction is "one click over the three big
// verdict buttons"; per-node review only appears when "需要修改" is picked (draft 2.2's
// "default only the coarsest grain, expand on demand" rule). "合并进上一个节点" is literally
// "merge into the previous node in this list" -- no free node-to-node picker, since the
// draft's own wording already fixes the target as the immediately preceding node.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { NodeVerdicts, PriorRecordDetail, PriorVerdict, Role } from "../api/types";
import { GOLD_STATUS_LABELS, VERDICT_LABELS } from "../api/types";
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
  const [annotatorName, setAnnotatorName] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.getPriorRecord(versionId, recordId).then((d) => {
      if (cancelled) return;
      setDetail(d);
      // Gold 标注需要独立标注（不能预填上一次的判定去引导这一次的结论），已完成仲裁的记录只读展示
      // 历史即可 -- 这里始终从空白开始，跟原来"预填链上最新判定"的单人链式标注行为不同。
      setVerdict(null);
      setNodeVerdicts({});
      setNote("");
      setAnnotatorName("");
      setExpanded(false);
    });
    return () => {
      cancelled = true;
    };
  }, [versionId, recordId]);

  function setNodeVerdict(nodeId: string, v: string) {
    setNodeVerdicts((prev) => ({ ...prev, [nodeId]: v }));
  }

  async function handleSave() {
    if (!verdict || !annotatorName.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await api.submitAnnotation(
        versionId, recordId, verdict, expanded ? nodeVerdicts : {}, note.trim() || null, annotatorName.trim(), role,
      );
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
  const isTerminal = detail.annotations.some((a) => a.role_in_process === "arbitration");
  const priorNames = detail.annotations
    .filter((a) => a.role_in_process === "independent")
    .map((a) => a.annotator_name);

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
            <div style={{ fontSize: 16, fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
              {detail.name}
              <span
                style={{
                  fontSize: 11, fontWeight: 600, borderRadius: 999, padding: "2px 10px",
                  background: detail.gold_status === "gold" ? "#fff7e6" : "#f1f5f9",
                  color: detail.gold_status === "gold" ? "#b45309" : "#667085",
                }}
              >
                {GOLD_STATUS_LABELS[detail.gold_status]}
              </span>
            </div>
            <div style={{ fontSize: 11.5, color: "#94a3b8", marginTop: 2 }}>
              {isTerminal
                ? "已完成仲裁，标注流程已结束（只读）"
                : priorNames.length > 0
                  ? `已有独立标注：${priorNames.join("、")}——这次需要换一个不同的人（Gold 需要两次真正独立的判断）`
                  : "尚未标注过，这次会作为第一次独立标注"}
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

        {!isTerminal && (
          <input
            value={annotatorName}
            onChange={(e) => setAnnotatorName(e.target.value)}
            placeholder="标注人姓名（必填，用于识别独立标注/仲裁）"
            style={{ width: "100%", boxSizing: "border-box", border: "1px solid #d0d5dd", borderRadius: 8, padding: "8px 10px", fontSize: 12.5, marginBottom: 8, fontFamily: "inherit" }}
          />
        )}

        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="备注（可选）：为什么需要修改或丢弃"
          rows={2}
          disabled={isTerminal}
          style={{ width: "100%", boxSizing: "border-box", border: "1px solid #d0d5dd", borderRadius: 8, padding: "8px 10px", fontSize: 12.5, marginBottom: 12, fontFamily: "inherit" }}
        />

        {error && <div style={{ color: "#991b1b", fontSize: 12, marginBottom: 8 }}>{error}</div>}

        {!isTerminal && (
          <button
            onClick={handleSave}
            disabled={!verdict || !annotatorName.trim() || saving}
            style={{
              width: "100%", border: "none", borderRadius: 8, padding: "10px 0", fontWeight: 600, fontSize: 13,
              background: !verdict || !annotatorName.trim() || saving ? "#e5e7eb" : "#0ca30c",
              color: !verdict || !annotatorName.trim() || saving ? "#94a3b8" : "#fff",
              cursor: !verdict || !annotatorName.trim() || saving ? "default" : "pointer",
            }}
          >
            {saving ? "保存中…" : priorNames.length >= 2 ? "提交仲裁判定" : "提交标注"}
          </button>
        )}

        {detail.annotations.length > 0 && (
          <div style={{ marginTop: 16, fontSize: 11.5, color: "#94a3b8" }}>
            标注历史（{detail.annotations.length} 次）：
            {detail.annotations
              .map((a) => `${VERDICT_LABELS[a.verdict]}（${a.annotator_name}${a.role_in_process === "arbitration" ? "・仲裁" : ""}）`)
              .join(" → ")}
          </div>
        )}
      </div>
    </>
  );
}
