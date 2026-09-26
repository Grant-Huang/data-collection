// Annotation panel -- IMPLEMENTATION_PLAN.md section 17.4: annotation is the same review
// conversation as creating/editing a workflow. The annotator talks to the agent about the
// graph ("第三步其实是班长做的", "少了通知班组长", "没问题"); the agent edits the annotator's own
// working copy, lists what it changed, and when the annotator is satisfied proposes a verdict
// (采纳 if nothing changed / 需要修改 with reason tags / 丢弃) that the annotator confirms by
// replying「确认」. Confirming writes the annotation (verdict + reasons + changes + corrected
// graph). No verdict buttons, no chips.
//
// Blind review is unchanged: the session only contains this annotator's messages and graph,
// and the record detail hides other people's conclusions until arbitration.
//
// Queue workflow: the dashboard passes its current filtered list; ←/→ (when not typing) move
// between records, Esc closes, and after submitting "下一条" goes straight on.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, apiErrorMessage } from "../api/client";
import type { PriorRecordDetail, ReviewSession, Role } from "../api/types";
import { GOLD_STATUS_LABELS, REASON_TAG_LABELS, STAGE_LABELS, VERDICT_LABELS } from "../api/types";
import { accessFor } from "../utils/annotationAccess";
import { AnnotationCard, RoundHistory, VERDICT_COLOR } from "./annotation/AnnotationCards";
import { ChatPanel } from "./ChatPanel";
import { DagView, type NodeDecoration } from "./DagView";

function isTypingTarget(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null;
  return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
}

const CHANGED_COLOR = "#0f766e";

export function PriorAnnotationPanel({
  versionId, recordId, role, queue, annotatorName, setAnnotatorName, onClose, onSaved, onNavigate,
}: {
  versionId: string;
  recordId: string;
  role: Role;
  queue: string[];
  annotatorName: string;
  setAnnotatorName: (name: string) => void;
  onClose: () => void;
  onSaved: () => void;
  onNavigate: (recordId: string) => void;
}) {
  const [detail, setDetail] = useState<PriorRecordDetail | null>(null);
  const [session, setSession] = useState<ReviewSession | null>(null);
  const [sending, setSending] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSignals, setShowSignals] = useState(false);
  const [showOriginal, setShowOriginal] = useState(false);
  const [insert, setInsert] = useState<{ text: string; nonce: number } | null>(null);
  const autoStarted = useRef(false);

  const loadDetail = useCallback(async () => {
    try {
      const d = await api.getPriorRecord(versionId, recordId);
      setDetail(d);
      return d;
    } catch (e) {
      setError(apiErrorMessage(e));
      return null;
    }
  }, [versionId, recordId]);

  const startSession = useCallback(async () => {
    if (!annotatorName.trim()) return;
    setStarting(true);
    setError(null);
    try {
      setSession(await api.startReviewSession(versionId, recordId, annotatorName.trim(), role));
    } catch (e) {
      setError(apiErrorMessage(e));
    } finally {
      setStarting(false);
    }
  }, [versionId, recordId, annotatorName, role]);

  // New record: reset, load, and -- if the annotator's name is known and they can act --
  // open (or resume) their review conversation right away.
  useEffect(() => {
    setDetail(null);
    setSession(null);
    setError(null);
    setShowSignals(false);
    setShowOriginal(false);
    autoStarted.current = false;
    loadDetail();
  }, [loadDetail]);

  const access = detail ? accessFor(detail, annotatorName) : null;
  useEffect(() => {
    if (!detail || autoStarted.current || detail.stage === "done" || !access?.canAct || !annotatorName.trim()) return;
    autoStarted.current = true;
    startSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail]);

  async function send(text: string, raw?: string) {
    if (!session) return;
    setSending(true);
    setError(null);
    // Optimistic: show the message immediately.
    setSession((s) => s && { ...s, turns: [...s.turns, { turn_id: `local-${Date.now()}`, role: "expert", text, raw_transcript: raw ?? null }] });
    try {
      const next = await api.reviewSessionTurn(versionId, session.session_id, text, raw);
      setSession(next);
      if (next.status === "submitted") {
        onSaved();
        loadDetail();
      }
    } catch (e) {
      setError(apiErrorMessage(e));
      // 409: the record moved on (e.g. someone else finished the arbitration).
      const d = await loadDetail();
      if (d) setSession((s) => s && { ...s, turns: s.turns.filter((t) => !t.turn_id.startsWith("local-")) });
    } finally {
      setSending(false);
    }
  }

  const idx = queue.indexOf(recordId);
  const prevId = idx > 0 ? queue[idx - 1] : null;
  const nextId = idx >= 0 && idx < queue.length - 1 ? queue[idx + 1] : queue.find((id) => id !== recordId) ?? null;

  const keyHandler = useRef<(e: KeyboardEvent) => void>(() => {});
  keyHandler.current = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      onClose();
      return;
    }
    if (isTypingTarget(e.target) || e.isComposing || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "ArrowRight" && nextId) onNavigate(nextId);
    else if (e.key === "ArrowLeft" && prevId) onNavigate(prevId);
  };
  useEffect(() => {
    const h = (e: KeyboardEvent) => keyHandler.current(e);
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  // Highlight what this annotator changed in their working copy.
  const decorations = useMemo(() => {
    if (!session) return undefined;
    const base = new Map(session.base_graph.nodes.map((n) => [n.node_id, n]));
    const d: Record<string, NodeDecoration> = {};
    for (const n of session.graph.nodes) {
      const b = base.get(n.node_id);
      if (!b) d[n.node_id] = { border: CHANGED_COLOR, badge: "新增", badgeColor: CHANGED_COLOR };
      else if (b.label !== n.label || JSON.stringify(b.actor_roles ?? []) !== JSON.stringify(n.actor_roles ?? []))
        d[n.node_id] = { border: CHANGED_COLOR, badge: "已改", badgeColor: CHANGED_COLOR };
    }
    return d;
  }, [session]);

  const submitted = session?.status === "submitted";
  const errorSignals = detail?.signals.filter((s) => s.level === "error").length ?? 0;
  const roundIndependents = (detail?.annotations ?? []).filter((a) => (a.round ?? 1) === detail?.round && a.role_in_process === "independent");
  const navBtn = (enabled: boolean) => ({
    border: "1px solid #d0d5dd", background: "#fff", borderRadius: 6, padding: "3px 10px", fontSize: 12,
    color: enabled ? "#475569" : "#cbd5e1", cursor: enabled ? "pointer" : "default",
  });
  const graphShown = session ? session.graph : detail && detail.stage === "done" && !showOriginal && detail.final_graph ? detail.final_graph : detail?.graph;

  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.35)", zIndex: 50 }} />
      <div
        style={{
          position: "fixed", top: "50%", left: "50%", transform: "translate(-50%, -50%)", zIndex: 51,
          width: 1180, maxWidth: "96vw", height: "90vh", display: "flex", flexDirection: "column",
          fontFamily: "-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif",
          background: "#fff", borderRadius: 12, boxShadow: "0 12px 40px rgba(0,0,0,0.25)", overflow: "hidden",
        }}
      >
        {/* Top bar: queue navigation + who I am + close */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, padding: "12px 20px", borderBottom: "1px solid #f1f3f5", flexWrap: "wrap" }}>
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
              disabled={!!session}
              placeholder="你的姓名（会记住）"
              style={{ width: 140, border: `1px solid ${annotatorName.trim() ? "#d0d5dd" : "#f59e0b"}`, borderRadius: 6, padding: "4px 8px", fontSize: 12 }}
            />
            <button
              onClick={onClose}
              aria-label="关闭"
              title="关闭（Esc）"
              style={{
                border: "none", background: "#f1f5f9", color: "#475569", borderRadius: 999, marginLeft: 4,
                width: 28, height: 28, fontSize: 15, lineHeight: 1, cursor: "pointer",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}
            >
              ✕
            </button>
          </div>
        </div>

        {!detail ? (
          <div style={{ color: error ? "#991b1b" : "#94a3b8", fontSize: 12.5, padding: 40, textAlign: "center" }}>{error ?? "加载中…"}</div>
        ) : (
          <>
            {/* Record header */}
            <div style={{ padding: "12px 20px 8px" }}>
              <div style={{ fontSize: 16, fontWeight: 700, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                {detail.name}
                <span style={{ fontSize: 11, fontWeight: 600, borderRadius: 999, padding: "2px 10px", background: "#eef4fc", color: "#2a78d6" }}>
                  {STAGE_LABELS[detail.stage]}
                </span>
                {detail.gold_status === "gold" && (
                  <span style={{ fontSize: 11, fontWeight: 600, borderRadius: 999, padding: "2px 10px", background: "#fff7e6", color: "#b45309" }}>
                    {GOLD_STATUS_LABELS.gold}
                  </span>
                )}
                {session && (
                  <span style={{ fontSize: 11.5, color: "#94a3b8", fontWeight: 400 }}>
                    {session.role_in_process === "arbitration" ? "你在仲裁" : "独立标注（看不到其他人的结论）"}
                  </span>
                )}
              </div>
              {detail.signals.length > 0 && (
                <div style={{ marginTop: 4, fontSize: 12 }}>
                  <button
                    onClick={() => setShowSignals((s) => !s)}
                    style={{ border: "none", background: "none", padding: 0, cursor: "pointer", color: errorSignals ? "#991b1b" : "#92400e", fontSize: 12 }}
                  >
                    {errorSignals ? "✖" : "⚠"} 机器预检信号 {detail.signals.length} 条（结构校验 / 近重复 / 疑似微工作流复用）{showSignals ? "▲" : "▼"}
                  </button>
                  {showSignals && (
                    <ul style={{ margin: "4px 0 0", paddingLeft: 18, color: "#475569" }}>
                      {detail.signals.map((s, i) => (
                        <li key={i} style={{ color: s.level === "error" ? "#991b1b" : undefined }}>{s.message}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              {access?.reason && detail.stage !== "done" && !session && (
                <div style={{ marginTop: 8, fontSize: 12, color: "#92400e", background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 6, padding: "6px 10px" }}>
                  {access.reason}——这条请留给其他人处理，可以按 → 跳到下一条。
                </div>
              )}
              {error && <div style={{ marginTop: 8, color: "#991b1b", fontSize: 12 }}>{error}</div>}
            </div>

            <div style={{ flex: 1, minHeight: 0, display: "grid", gridTemplateColumns: session ? "1fr 1fr" : "1fr", borderTop: "1px solid #f1f3f5" }}>
              {/* Graph column */}
              <div style={{ minHeight: 0, overflowY: "auto", padding: "12px 16px", borderRight: session ? "1px solid #f1f3f5" : undefined }}>
                {session?.role_in_process === "arbitration" && roundIndependents.length > 0 && (
                  <details open style={{ marginBottom: 10, fontSize: 12 }}>
                    <summary style={{ cursor: "pointer", color: "#475569", fontWeight: 600 }}>两位标注人的结果</summary>
                    <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                      {roundIndependents.slice(0, 2).map((a) => <AnnotationCard key={a.annotation_id} a={a} />)}
                    </div>
                  </details>
                )}
                {detail.stage === "done" && !session && (
                  <div style={{ marginBottom: 8, fontSize: 13 }}>
                    最终结论：
                    <b style={{ color: detail.final_verdict ? VERDICT_COLOR[detail.final_verdict] : undefined }}>
                      {detail.final_verdict ? VERDICT_LABELS[detail.final_verdict] : "—"}
                    </b>
                    {detail.final_graph && (
                      <span style={{ marginLeft: 10 }}>
                        {[false, true].map((orig) => (
                          <button
                            key={String(orig)}
                            onClick={() => setShowOriginal(orig)}
                            style={{
                              border: `1px solid ${showOriginal === orig ? "#2a78d6" : "#d0d5dd"}`, color: showOriginal === orig ? "#2a78d6" : "#667085",
                              background: "#fff", borderRadius: 6, padding: "2px 10px", cursor: "pointer", fontSize: 12, marginLeft: 4,
                            }}
                          >
                            {orig ? "原始图" : "修正后的图"}
                          </button>
                        ))}
                      </span>
                    )}
                  </div>
                )}
                {session && (
                  <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 6 }}>
                    这是你的工作副本，绿色是你改过的步骤。点一下步骤，会把它的名字填进输入框。
                  </div>
                )}
                {graphShown && (
                  <div style={{ border: "1px solid #e5e7eb", borderRadius: 8 }}>
                    <DagView
                      graph={graphShown}
                      readOnly
                      scrollable
                      nodeDecorations={decorations}
                      onNodeTap={session && !submitted ? (n) => setInsert({ text: `「${n.label}」`, nonce: Date.now() }) : undefined}
                    />
                  </div>
                )}
                {detail.stage === "done" && !session && <RoundHistory detail={detail} />}
                {!session && detail.stage !== "done" && access?.canAct && (
                  <div style={{ marginTop: 12, fontSize: 12.5, color: "#475569" }}>
                    {annotatorName.trim() ? (
                      <button
                        onClick={startSession}
                        disabled={starting}
                        style={{ border: "none", background: "#2a78d6", color: "#fff", borderRadius: 8, padding: "8px 18px", fontWeight: 600, cursor: "pointer" }}
                      >
                        {starting ? "正在打开…" : `以「${annotatorName.trim()}」的身份开始标注`}
                      </button>
                    ) : (
                      "先在右上角填写你的姓名，再开始标注。"
                    )}
                  </div>
                )}
              </div>

              {/* Conversation column */}
              {session && (
                <div style={{ minHeight: 0, display: "flex", flexDirection: "column" }}>
                  <div style={{ flex: 1, minHeight: 0 }}>
                    <ChatPanel
                      turns={session.turns}
                      graph={session.graph}
                      nextQuestion={null}
                      onSend={send}
                      sending={sending}
                      confirmed={session.status !== "active"}
                      insertText={insert}
                      placeholder={
                        session.status === "active"
                          ? "直接说哪里不对、缺了什么；都对就回复「确认」。Enter 发送，Shift+Enter 换行"
                          : session.status === "submitted" ? "这次标注已提交" : "这次标注已失效"
                      }
                    />
                  </div>
                  {submitted && (
                    <div style={{ padding: "10px 16px", borderTop: "1px solid #e5e7eb", display: "flex", alignItems: "center", gap: 10, background: "#f6fef6" }}>
                      <div style={{ flex: 1, fontSize: 12.5 }}>
                        已提交：
                        {session.proposal && (
                          <b style={{ color: VERDICT_COLOR[session.proposal.verdict] }}>{VERDICT_LABELS[session.proposal.verdict]}</b>
                        )}
                        {session.proposal?.reason_tags.length
                          ? `（${session.proposal.reason_tags.map((t) => REASON_TAG_LABELS[t]).join("、")}）`
                          : ""}
                      </div>
                      {nextId && (
                        <button
                          onClick={() => onNavigate(nextId)}
                          style={{ border: "none", background: "#2a78d6", color: "#fff", borderRadius: 6, padding: "6px 14px", fontWeight: 600, cursor: "pointer" }}
                        >
                          下一条 →
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </>
  );
}
