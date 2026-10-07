// B1: "AI is working" status line with a live elapsed timer, modelled on Claude Code's
// "Generating… 3m 16s". Shown as an assistant bubble at the bottom of the chat while a turn is
// in flight, so the expert can tell "still working" from "stuck" -- building the graph from a
// long narration can legitimately take a minute or more with the local model (the extraction
// call's timeout is 180s, see backend review_agent.EXTRACT_TIMEOUT).
import { useEffect, useState } from "react";

// After this long, add a reassurance line under the timer.
const SLOW_AFTER_S = 15;

/** 3 -> "3s", 65 -> "1m 05s", 196 -> "3m 16s" */
export function formatElapsed(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

export function ThinkingIndicator({ label }: { label: string }) {
  // The timer starts when the bubble mounts, i.e. when the expert hits 发送.
  const [startedAt] = useState(() => Date.now());
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => setElapsed((Date.now() - startedAt) / 1000), 1000);
    return () => window.clearInterval(id);
  }, [startedAt]);

  return (
    <div className="chat-row bot" role="status" aria-label={label}>
      <div className="chat-avatar" aria-hidden>AI</div>
      <div className="chat-bubble chat-thinking">
        <div className="chat-thinking-line">
          <span className="chat-spinner" aria-hidden />
          <span>{label}</span>
          <span className="chat-thinking-time">{formatElapsed(elapsed)}</span>
        </div>
        {elapsed >= SLOW_AFTER_S && (
          <div className="chat-thinking-hint">
            内容较多时需要一两分钟，AI 还在处理，请稍等。万一失败，你刚才的话会放回输入框，可以直接重发。
          </div>
        )}
      </div>
    </div>
  );
}

// What the AI is doing for a message, for the indicator text. The 「讲完了」 signal during the
// narration is the slow one (it builds the whole graph); a narration piece is only noted down.
const NARRATIVE_DONE = /^(我)?(讲完了?|说完了?|就这些|就这么多|没有了|没了|完了|好了|整理吧|开始整理|重试)(吧|了|啦|啊|呀)?[。！!.]?$/;

export function isNarrativeDone(text: string): boolean {
  return NARRATIVE_DONE.test(text.trim());
}

export function thinkingLabel(stage: string | undefined, lastSent: string | null): string {
  if (stage === "review_narrative") {
    return lastSent && isNarrativeDone(lastSent) ? "正在整理流程图…" : "正在记录…";
  }
  return "正在理解你的回答，更新流程图…";
}
