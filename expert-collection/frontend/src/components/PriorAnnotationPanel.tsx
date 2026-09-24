// Prior / Gold annotation panel -- design/case_context_and_prior_annotation_draft.md section 2,
// IMPLEMENTATION_PLAN.md sections 9.2 / 9 §9 Phase C-2 / 15.
//
// One panel, four modes driven by the record's `stage` (computed by the backend):
// - independent review (first/second_review): BLIND -- the backend sends nobody else's
//   verdicts, and this panel shows no history. Three big verdict buttons (keys 1/2/3); for
//   "需要修改"/"丢弃" at least one structured reason tag is required; node-level judgements
//   are made by clicking nodes on the graph (clicking a node switches to "需要修改").
// - arbitration: the two independent annotations side by side, nodes they disagree on
//   highlighted on the graph, then the arbitrator's own judgement with the same controls.
// - rework: ReworkEditor (turn the suggestions into a corrected graph).
// - done: read-only outcome + full history.
//
// Queue workflow: the dashboard passes the ids of its current filtered list; "提交并下一条"
// (Enter) saves and moves straight to the next record, ←/→ move without saving, Esc closes.
// The annotator name comes from useAnnotatorName (remembered per browser), and "you can't act
// on this record" is decided up front from the round's participant names, not after submit.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, apiErrorMessage } from "../api/client";
import type { NodeVerdicts, PriorRecordDetail, PriorVerdict, ReasonTag, Role } from "../api/types";
import { GOLD_STATUS_LABELS, REASON_TAG_LABELS, STAGE_LABELS, VERDICT_LABELS } from "../api/types";
import { accessFor, parseVerdict, verdictDecorations } from "../utils/annotationAccess";
import { AnnotationCard, RoundHistory, VERDICT_COLOR } from "./annotation/AnnotationCards";
import { NodeActionBar } from "./annotation/NodeActionBar";
import { ReworkEditor } from "./annotation/ReworkEditor";
import { DagView, type NodeDecoration } from "./DagView";

const VERDICTS: PriorVerdict[] = ["accepted", "needs_revision", "rejected"];
const REASON_TAGS = Object.keys(REASON_TAG_LABELS) as ReasonTag[];
const DIFF_COLOR = "#f59e0b";

function isTypingTarget(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null;
  return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
}

export function PriorAnnotationPanel({
  versionId, recordId, role, queue, annotatorName, setAnnotatorName, onClose, onSaved, onNavigate,
}: {
  versionId: string;
  recordId: string;
  role: Role;
  queue: string[]; // record ids in the dashboard's current list order, for prev/next
  annotatorName: string;
  setAnnotatorName: (name: string) => void;
  onClose: () => void;
  onSaved: () => void;
  onNavigate: (recordId: string) => void;
}) {
  const [detail, setDetail] = useState<PriorRecordDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [verdict, setVerdict] = useState<PriorVerdict | null>(null);
  const [nodeVerdicts, setNodeVerdicts] = useState<NodeVerdicts>({});
  const [reasonTags, setReasonTags] = useState<ReasonTag[]>([]);
  const [note, setNote] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSignals, setShowSignals] = useState(false);
  const [showOriginal, setShowOriginal] = useState(false);

  const load = useCallback(() => {
    let cancelled = false;
    setLoadError(null);
    api.getPriorRecord(versionId, recordId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((e) => {
        if (!cancelled) setLoadError(apiErrorMessage(e));
      });
    return () => {
      cancelled = true;
    };
  }, [versionId, recordId]);

  useEffect(() => {
    // Every record starts from a blank form -- Gold needs genuinely independent judgements,
    // so nothing is prefilled from anyone else's annotation.
    setDetail(null);
    setVerdict(null);
    setNodeVerdicts({});
    setReasonTags([]);
    setNote("");
    setSelectedId(null);
    setError(null);
    setShowSignals(false);
    setShowOriginal(false);
    return load();
  }, [load]);

  const idx = queue.indexOf(recordId);
  const prevId = idx > 0 ? queue[idx - 1] : null;
  const nextId = idx >= 0 && idx < queue.length - 1 ? queue[idx + 1] : queue.find((id) => id !== recordId) ?? null;

  const access = detail ? accessFor(detail, annotatorName) : null;
  const mode = !detail ? null : detail.stage === "rework" ? "rework" : detail.stage === "done" ? "done" : "review";
  const isArbitration = detail?.stage === "arbitration";
  const canReview = mode === "review" && !!access?.canAct;
  const needsReason = verdict === "needs_revision" || verdict === "rejected";
  const missing = !annotatorName.trim()
    ? "请先填写标注人姓名"
    : !verdict
      ? "请选择整体判定（1 / 2 / 3）"
      : needsReason && reasonTags.length === 0
        ? "请至少勾选一个原因标签"
        : reasonTags.includes("other") && !note.trim()
          ? "勾选了「其他」，请在备注里写明原因"
          : null;
  const canSubmit = canReview && !missing && !saving;

  // Arbitration: the round's two independent annotations and the nodes they disagree on.
  const roundIndependents = useMemo(
    () => (detail?.annotations ?? []).filter((a) => (a.round ?? 1) === detail?.round && a.role_in_process === "independent"),
    [detail],
  );
  const disputedNodes = useMemo(() => {
    if (!isArbitration || roundIndependents.length < 2) return new Set<string>();
    const [a, b] = roundIndependents;
    const ids = new Set([...Object.keys(a.node_verdicts), ...Object.keys(b.node_verdicts)]);
    return new Set([...ids].filter((id) => (a.node_verdicts[id] ?? "keep") !== (b.node_verdicts[id] ?? "keep")));
  }, [isArbitration, roundIndependents]);

  const decorations = useMemo(() => {
    const d: Record<string, NodeDecoration> = {};
    for (const id of disputedNodes) d[id] = { border: DIFF_COLOR, badge: "分歧", badgeColor: DIFF_COLOR };
    const mine = verdictDecorations(verdict === "needs_revision" ? nodeVerdicts : {}, selectedId);
    for (const [id, deco] of Object.entries(mine)) d[id] = { ...(d[id] ?? {}), ...deco };
    return d;
  }, [disputedNodes, verdict, nodeVerdicts, selectedId]);

  const submit = useCallback(async (andNext: boolean) => {
    if (!detail || !canSubmit || !verdict) return;
    setSaving(true);
    setError(null);
    try {
      await api.submitAnnotation(versionId, recordId, {
        verdict,
        node_verdicts: verdict === "needs_revision" ? nodeVerdicts : {},
        reason_tags: verdict === "accepted" ? [] : reasonTags,
        note: note.trim() || null,
        annotator_name: annotatorName.trim(),
        actor_role: role,
        round: detail.round,
      });
      onSaved();
      if (andNext && nextId) onNavigate(nextId);
      else onClose();
    } catch (e) {
      setError(apiErrorMessage(e));
    } finally {
      setSaving(false);
    }
  }, [detail, canSubmit, verdict, versionId, recordId, nodeVerdicts, reasonTags, note, annotatorName, role, onSaved, nextId, onNavigate, onClose]);

  function pickVerdict(v: PriorVerdict) {
    setVerdict(v);
    if (v === "accepted") setSelectedId(null);
  }

  // Keyboard shortcuts (Prodigy-style: one decision per key). Ignored while typing.
  const keyHandler = useRef<(e: KeyboardEvent) => void>(() => {});
  keyHandler.current = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      onClose();
      return;
    }
    if (isTypingTarget(e.target) || e.isComposing || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "ArrowRight" && nextId) onNavigate(nextId);
    else if (e.key === "ArrowLeft" && prevId) onNavigate(prevId);
    else if (canReview && ["1", "2", "3"].includes(e.key)) pickVerdict(VERDICTS[Number(e.key) - 1]);
    else if (e.key === "Enter" && canSubmit) {
      e.preventDefault();
      void submit(true);
    }
  };
  useEffect(() => {
    const h = (e: KeyboardEvent) => keyHandler.current(e);
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  const selectedNode = detail?.graph.nodes.find((n) => n.node_id === selectedId) ?? null;
  const errorSignals = detail?.signals.filter((s) => s.level === "error").length ?? 0;

  const navBtn = (enabled: boolean) => ({
    border: "1px solid #d0d5dd", background: "#fff", borderRadius: 6, padding: "3px 10px", fontSize: 12,
    color: enabled ? "#475569" : "#cbd5e1", cursor: enabled ? "pointer" : "default",
  });

  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.35)", zIndex: 50 }} />
      <div
        style={{
          position: "fixed", top: "50%", left: "50%", transform: "translate(-50%, -50%)", zIndex: 51,
          width: mode === "rework" ? 980 : 760, maxWidth: "94vw", maxHeight: "90vh", overflowY: "auto",
          background: "#fff", borderRadius: 12, padding: 24, boxShadow: "0 12px 40px rgba(0,0,0,0.25)", boxSizing: "border-box",
        }}
      >
        {/* Top bar: queue navigation + who I am + close. Sticky, because the panel body scrolls
            (graph + annotation controls are often taller than the viewport) and the close button
            must stay reachable -- carried over from main's PriorAnnotationPanel fix. */}
        <div
          style={{
            position: "sticky", top: -24, zIndex: 2, background: "#fff",
            marginLeft: -24, marginRight: -24, marginTop: -24, padding: "16px 24px 10px",
            display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginBottom: 12, flexWrap: "wrap",
            borderBottom: "1px solid #f1f3f5",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <button disabled={!prevId} onClick={() => prevId && onNavigate(prevId)} style={navBtn(!!prevId)}>← 上一条</button>
            <span style={{ fontSize: 12, color: "#94a3b8" }}>{idx >= 0 ? `${idx + 1} / ${queue.length}` : "不在当前列表中"}</span>
            <button disabled={!nextId} onClick={() => nextId && onNavigate(nextId)} style={navBtn(!!nextId)}>下一条 →</button>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 12, color: "#667085" }}>标注人</span>
            <input
              value={annotatorName}
              onChange={(e) => setAnnotatorName(e.target.value)}
              placeholder="你的姓名（会记住）"
              style={{ width: 140, border: `1px solid ${annotatorName.trim() ? "#d0d5dd" : "#f59e0b"}`, borderRadius: 6, padding: "4px 8px", fontSize: 12 }}
            />
            <button
              onClick={onClose}
              aria-label="关闭"
              title="关闭（Esc）"
              style={{
                border: "none", background: "#f1f5f9", color: "#475569", borderRadius: 999, marginLeft: 4,
                width: 28, height: 28, fontSize: 15, lineHeight: 1, cursor: "pointer", flexShrink: 0,
                display: "flex", alignItems: "center", justifyContent: "center",
              }}
            >
              ✕
            </button>
          </div>
        </div>

        {loadError && <div style={{ color: "#991b1b", fontSize: 12.5 }}>{loadError}</div>}
        {!detail && !loadError && <div style={{ color: "#94a3b8", fontSize: 12.5, padding: "40px 0", textAlign: "center" }}>加载中…</div>}

        {detail && access && (
          <>
            {/* Header */}
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 16, fontWeight: 700, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                {detail.name}
                <span style={{ fontSize: 11, fontWeight: 600, borderRadius: 999, padding: "2px 10px", background: "#eef4fc", color: "#2a78d6" }}>
                  {STAGE_LABELS[detail.stage]}
                  {detail.round > 1 && `・第 ${detail.round} 轮`}
                </span>
                {detail.gold_status === "gold" && (
                  <span style={{ fontSize: 11, fontWeight: 600, borderRadius: 999, padding: "2px 10px", background: "#fff7e6", color: "#b45309" }}>
                    {GOLD_STATUS_LABELS.gold}
                  </span>
                )}
              </div>
              <div style={{ fontSize: 11.5, color: "#94a3b8", marginTop: 4 }}>
                {detail.blind
                  ? `独立标注（盲标）：看不到其他人的结论。${detail.round_annotator_names.length > 0 ? `本轮已有 ${detail.round_annotator_names.join("、")} 标注过。` : "你是本轮第一位标注人。"}${detail.round > 1 ? `这是返工后的修正图（返工人：${detail.round_reworker_name}）。` : ""}`
                  : isArbitration
                    ? "两位独立标注人结论不一致，请对照下方两份标注后给出仲裁判定。图上橙色标记的是两人判定不同的节点。"
                    : mode === "rework"
                      ? "本轮结论为「需要修改」：请把修改建议落实成修正后的图，提交后进入下一轮双人独立标注。"
                      : `标注流程已结束，最终结论：${detail.final_verdict ? VERDICT_LABELS[detail.final_verdict] : "—"}`}
              </div>
              {access.reason && (
                <div style={{ marginTop: 8, fontSize: 12, color: "#92400e", background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 6, padding: "6px 10px" }}>
                  {access.reason}——这条请留给其他人处理，可以按 → 跳到下一条。
                </div>
              )}
            </div>

            {/* Machine signals (visible even in blind mode: they're not human verdicts) */}
            {detail.signals.length > 0 && (
              <div style={{ marginBottom: 10, fontSize: 12 }}>
                <button
                  onClick={() => setShowSignals((s) => !s)}
                  style={{ border: "none", background: "none", padding: 0, cursor: "pointer", color: errorSignals ? "#991b1b" : "#92400e", fontSize: 12 }}
                >
                  {errorSignals ? "✖" : "⚠"} 机器预检信号 {detail.signals.length} 条（结构校验 / 近重复 / 疑似微工作流复用）{showSignals ? "▲" : "▼"}
                </button>
                {showSignals && (
                  <ul style={{ margin: "6px 0 0", paddingLeft: 18, color: "#475569" }}>
                    {detail.signals.map((s, i) => (
                      <li key={i} style={{ color: s.level === "error" ? "#991b1b" : undefined }}>{s.message}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {mode === "rework" && (
              access.canAct ? (
                <ReworkEditor
                  versionId={versionId}
                  detail={detail}
                  reworkerName={annotatorName}
                  role={role}
                  onSubmitted={() => {
                    onSaved();
                    if (nextId) onNavigate(nextId);
                    else onClose();
                  }}
                />
              ) : null
            )}

            {mode !== "rework" && (
              <>
                {isArbitration && roundIndependents.length >= 2 && (
                  <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
                    {roundIndependents.slice(0, 2).map((a) => (
                      <AnnotationCard key={a.annotation_id} a={a} graph={detail.graph} />
                    ))}
                  </div>
                )}

                {mode === "done" && detail.revisions.length > 0 && (
                  <div style={{ display: "flex", gap: 6, marginBottom: 6, fontSize: 12 }}>
                    {[false, true].map((orig) => (
                      <button
                        key={String(orig)}
                        onClick={() => setShowOriginal(orig)}
                        style={{
                          border: `1px solid ${showOriginal === orig ? "#2a78d6" : "#d0d5dd"}`, color: showOriginal === orig ? "#2a78d6" : "#667085",
                          background: "#fff", borderRadius: 6, padding: "2px 10px", cursor: "pointer",
                        }}
                      >
                        {orig ? "原始图" : "最终图"}
                      </button>
                    ))}
                  </div>
                )}

                {/* Fit-to-width + vertical scroll (same mode as the mobile DAG page), so labels stay
                    readable instead of the whole graph being shrunk into a short box. */}
                <div style={{ maxHeight: 420, overflowY: "auto", border: "1px solid #e5e7eb", borderRadius: 8, marginBottom: 8 }}>
                  <DagView
                    graph={mode === "done" && showOriginal ? detail.original_graph : detail.graph}
                    readOnly
                    scrollable
                    nodeDecorations={mode === "review" ? decorations : undefined}
                    onNodeTap={canReview ? (n) => {
                      setSelectedId(n.node_id);
                      if (verdict !== "needs_revision") setVerdict("needs_revision");
                    } : undefined}
                  />
                </div>
                {canReview && (
                  <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 10 }}>
                    点图上的节点可逐个判定（删除 / 合并进前驱），会自动切换到「需要修改」。
                  </div>
                )}

                {canReview && selectedNode && verdict === "needs_revision" && (
                  <NodeActionBar
                    graph={detail.graph}
                    node={selectedNode}
                    verdict={nodeVerdicts[selectedNode.node_id]}
                    onVerdict={(v) => setNodeVerdicts((prev) => {
                      const next = { ...prev };
                      if (v === "keep") delete next[selectedNode.node_id];
                      else next[selectedNode.node_id] = v;
                      return next;
                    })}
                    onClose={() => setSelectedId(null)}
                  />
                )}

                {canReview && (
                  <>
                    <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
                      {VERDICTS.map((v, i) => (
                        <button
                          key={v}
                          onClick={() => pickVerdict(v)}
                          style={{
                            flex: 1, border: verdict === v ? "none" : "1px solid #d0d5dd",
                            borderRadius: 8, padding: "10px 0", fontSize: 13, fontWeight: 600, cursor: "pointer",
                            background: verdict === v ? VERDICT_COLOR[v] : "#fff",
                            color: verdict === v ? "#fff" : "#475569",
                          }}
                        >
                          {VERDICT_LABELS[v]}
                          <span style={{ marginLeft: 6, fontSize: 11, opacity: 0.7 }}>[{i + 1}]</span>
                        </button>
                      ))}
                    </div>

                    {verdict === "needs_revision" && Object.keys(nodeVerdicts).length > 0 && (
                      <div style={{ fontSize: 12, color: "#475569", marginBottom: 8 }}>
                        已标记节点：
                        {Object.entries(nodeVerdicts).map(([id, v]) => {
                          const label = detail.graph.nodes.find((n) => n.node_id === id)?.label ?? id;
                          const p = parseVerdict(v);
                          return (
                            <span key={id} style={{ marginRight: 10 }}>
                              「{label}」{p.kind === "delete" ? "删除" : "合并"}
                            </span>
                          );
                        })}
                      </div>
                    )}

                    {needsReason && (
                      <div style={{ marginBottom: 10 }}>
                        <div style={{ fontSize: 12, fontWeight: 700, color: "#667085", marginBottom: 6 }}>原因（至少选一个）</div>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                          {REASON_TAGS.map((t) => {
                            const on = reasonTags.includes(t);
                            return (
                              <button
                                key={t}
                                onClick={() => setReasonTags((prev) => (on ? prev.filter((x) => x !== t) : [...prev, t]))}
                                style={{
                                  border: `1px solid ${on ? "#2a78d6" : "#d0d5dd"}`, color: on ? "#2a78d6" : "#475569",
                                  background: on ? "#eef4fc" : "#fff", borderRadius: 999, padding: "3px 12px", fontSize: 12, cursor: "pointer",
                                }}
                              >
                                {REASON_TAG_LABELS[t]}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    <textarea
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder={reasonTags.includes("other") ? "备注（必填）：请写明「其他」原因" : "备注（可选）：补充说明"}
                      rows={2}
                      style={{ width: "100%", boxSizing: "border-box", border: "1px solid #d0d5dd", borderRadius: 8, padding: "8px 10px", fontSize: 12.5, marginBottom: 10, fontFamily: "inherit" }}
                    />

                    {error && <div style={{ color: "#991b1b", fontSize: 12, marginBottom: 8 }}>{error}</div>}

                    <div style={{ display: "flex", gap: 8 }}>
                      <button
                        onClick={() => submit(true)}
                        disabled={!canSubmit}
                        style={{
                          flex: 2, border: "none", borderRadius: 8, padding: "10px 0", fontWeight: 600, fontSize: 13,
                          background: canSubmit ? "#0ca30c" : "#e5e7eb", color: canSubmit ? "#fff" : "#94a3b8",
                          cursor: canSubmit ? "pointer" : "default",
                        }}
                      >
                        {saving ? "保存中…" : missing ?? `${isArbitration ? "提交仲裁" : "提交"}并下一条 [Enter]`}
                      </button>
                      <button
                        onClick={() => submit(false)}
                        disabled={!canSubmit}
                        style={{
                          flex: 1, border: "1px solid #d0d5dd", borderRadius: 8, padding: "10px 0", fontSize: 13,
                          background: "#fff", color: canSubmit ? "#475569" : "#cbd5e1", cursor: canSubmit ? "pointer" : "default",
                        }}
                      >
                        提交并关闭
                      </button>
                    </div>
                    <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 8, textAlign: "center" }}>
                      快捷键：1 采纳 ・ 2 需要修改 ・ 3 丢弃 ・ Enter 提交并下一条 ・ ← / → 切换记录 ・ Esc 关闭
                    </div>
                  </>
                )}

                {mode === "done" && <RoundHistory detail={detail} />}
              </>
            )}

            {/* Earlier rounds only -- the current round's suggestions are already shown in the editor. */}
            {mode === "rework" && detail.round > 1 && (
              <RoundHistory
                detail={{ ...detail, round: detail.round - 1, annotations: detail.annotations.filter((a) => (a.round ?? 1) < detail.round) }}
              />
            )}
          </>
        )}
      </div>
    </>
  );
}
