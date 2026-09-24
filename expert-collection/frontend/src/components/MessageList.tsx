// Shared bubble rendering between desktop ChatPanel and the mobile chat page, so message
// styling stays identical across both views per PRD 4.3 ("与桌面端消息样式一致").
//
// An assistant message is rendered in three layers (design/conversation-chips-redesign.html):
//   1. ack      -- muted restatement of what was just recorded, plus a "图上 +N" tag for the
//                  nodes the expert's previous message produced (hover highlights them on the
//                  desktop DAG);
//   2. question -- the one thing being asked (main text);
//   3. why      -- one line under the bubble, only on the latest question.
// Chips sit directly under the question they belong to: interactive for the current one,
// frozen (with the pick highlighted) for answered ones. Older records without the layered
// fields fall back to the plain `text`.
import { useEffect, useRef, type ReactNode } from "react";
import type { ConversationTurn, Graph, NextQuestion } from "../api/types";
import { isFallbackChip, pickedChips } from "../utils/chips";
import { QuickReplies } from "./QuickReplies";

// Node types worth counting in the "+N" tag -- the structural helpers (split/join/merge)
// are drawing mechanics, not something the expert said.
const CONTENT_NODE_TYPES = new Set(["start", "activity", "decision", "approval", "handoff", "wait", "end"]);

interface Props {
  turns: ConversationTurn[];
  graph?: Graph | null;
  // The question currently awaiting an answer; its chips render interactively under the
  // last assistant bubble. Omit/null when the session is confirmed or there is none.
  activeQuestion?: NextQuestion | null;
  onChipPick?: (text: string) => void;
  sending?: boolean;
  onHighlightNodes?: (nodeIds: string[] | null) => void;
  emptyState?: ReactNode;
}

export function MessageList({ turns, graph, activeQuestion, onChipPick, sending, onHighlightNodes, emptyState }: Props) {
  const listRef = useRef<HTMLDivElement>(null);

  // Keep the newest message (and the typing indicator) in view.
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns.length, sending, activeQuestion?.question]);

  function nodesFromTurn(turnId: string | undefined): string[] {
    if (!graph || !turnId) return [];
    return graph.nodes
      .filter((n) => n.source_turn_ids.includes(turnId) && CONTENT_NODE_TYPES.has(n.node_type))
      .map((n) => n.node_id);
  }

  return (
    <div ref={listRef} className="chat-list" aria-live="polite">
      {turns.length === 0 && emptyState}
      {turns.map((t, i) => {
        if (t.role === "expert") {
          return (
            <div key={t.turn_id} className="chat-row expert">
              <div className="chat-bubble">{t.text}</div>
            </div>
          );
        }

        const isLast = i === turns.length - 1;
        const prev = turns[i - 1];
        const next = turns[i + 1];
        const deltaIds = prev?.role === "expert" ? nodesFromTurn(prev.turn_id) : [];
        const layered = !!t.question;
        const chips = t.chips ?? [];
        const interactive = isLast && !sending && !!activeQuestion?.chips?.length && !!onChipPick;
        const picked = pickedChips(chips, next?.role === "expert" ? next.text : undefined);

        return (
          <div key={t.turn_id} className="chat-group">
            <div className="chat-row bot">
              <div className="chat-avatar" aria-hidden>AI</div>
              <div className="chat-bubble">
                {layered ? (
                  <>
                    {(t.ack || deltaIds.length > 0) && (
                      <div className="chat-ack">
                        {t.ack && <span>{t.ack}</span>}
                        {deltaIds.length > 0 && (
                          <span
                            className="chat-delta-tag"
                            title="这一轮在流程图上新增的内容"
                            onMouseEnter={() => onHighlightNodes?.(deltaIds)}
                            onMouseLeave={() => onHighlightNodes?.(null)}
                          >
                            图上 +{deltaIds.length}
                          </span>
                        )}
                      </div>
                    )}
                    <div className="chat-question">{t.question}</div>
                  </>
                ) : (
                  t.text
                )}
              </div>
            </div>
            {isLast && t.why && <div className="chat-why">为什么问：{t.why}</div>}
            {interactive && activeQuestion ? (
              <QuickReplies question={activeQuestion} onPick={onChipPick!} />
            ) : (
              chips.length > 0 && !isLast && (
                <div className="chat-chips" aria-label="当时的选项">
                  {chips.map((c) => (
                    <span
                      key={c}
                      className={["chip", "frozen", isFallbackChip(c) ? "fallback" : "", picked.has(c) ? "picked" : ""]
                        .filter(Boolean)
                        .join(" ")}
                    >
                      {c}
                    </span>
                  ))}
                </div>
              )
            )}
          </div>
        );
      })}
      {sending && (
        <div className="chat-row bot" aria-label="正在整理">
          <div className="chat-avatar" aria-hidden>AI</div>
          <div className="chat-bubble">
            <span className="chat-typing"><span /><span /><span /></span>
          </div>
        </div>
      )}
    </div>
  );
}
