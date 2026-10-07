// Shared bubble rendering between desktop ChatPanel and the mobile chat page, so message
// styling stays identical across both views per PRD 4.3 ("与桌面端消息样式一致").
//
// B4: keeps the newest message in view -- jumps to the bottom when a session is opened, and
// follows new messages as long as the expert is already near the bottom. If they have
// scrolled up to re-read history, it does not yank them back down; a "↓ 有新消息" button
// appears instead.
// B1: while a turn is being processed, an assistant-side status bubble with a live elapsed
// timer is shown at the bottom (Claude Code style: "正在理解你的回答… 3s").
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ConversationTurn } from "../api/types";
import { ThinkingIndicator } from "./ThinkingIndicator";

// How close to the bottom (px) still counts as "reading the latest message".
const NEAR_BOTTOM_PX = 80;

interface Props {
  turns: ConversationTurn[];
  // Changes when a different session is opened -- always jump straight to the bottom then.
  sessionKey?: string;
  // True while the AI is processing the expert's last message.
  pending?: boolean;
}

export function MessageList({ turns, sessionKey, pending = false }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [nearBottom, setNearBottom] = useState(true);
  const [hasUnseen, setHasUnseen] = useState(false);

  function scrollToBottom(smooth: boolean) {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
    setHasUnseen(false);
  }

  // Opening a session: always start at the newest message, no animation.
  useLayoutEffect(() => {
    scrollToBottom(false);
    setNearBottom(true);
  }, [sessionKey]);

  // New message or the thinking bubble appearing/disappearing.
  const lastTurn = turns[turns.length - 1];
  useEffect(() => {
    // The expert's own message always scrolls into view -- they just sent it.
    if (nearBottom || lastTurn?.role === "expert") scrollToBottom(true);
    else setHasUnseen(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [turns.length, pending]);

  function handleScroll() {
    const el = scrollRef.current;
    if (!el) return;
    const isNear = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
    setNearBottom(isNear);
    if (isNear) setHasUnseen(false);
  }

  return (
    <div style={{ flex: 1, minHeight: 0, position: "relative", display: "flex", flexDirection: "column" }}>
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        style={{ flex: 1, overflowY: "auto", padding: "16px", display: "flex", flexDirection: "column", gap: 12 }}
      >
        {turns.map((t) => (
          <div
            key={t.turn_id}
            style={{
              alignSelf: t.role === "expert" ? "flex-end" : "flex-start",
              maxWidth: "82%",
              background: t.role === "expert" ? "#2a78d6" : "#f1f3f5",
              color: t.role === "expert" ? "#fff" : "#1f2937",
              borderRadius: 12,
              padding: "8px 12px",
              fontSize: 13.5,
              lineHeight: 1.5,
              whiteSpace: "pre-wrap",
            }}
          >
            {t.text}
          </div>
        ))}
        {pending && <ThinkingIndicator />}
      </div>
      {hasUnseen && (
        <button
          onClick={() => scrollToBottom(true)}
          style={{
            position: "absolute", bottom: 10, left: "50%", transform: "translateX(-50%)",
            border: "1px solid #d0d5dd", background: "#fff", color: "#2a78d6", borderRadius: 999,
            padding: "6px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
            boxShadow: "0 2px 8px rgba(15,23,42,0.12)",
          }}
        >
          ↓ 有新消息
        </button>
      )}
    </div>
  );
}
