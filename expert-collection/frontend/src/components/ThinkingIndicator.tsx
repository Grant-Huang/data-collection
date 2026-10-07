// B1: "AI is working" status bubble with a live elapsed timer, modelled on Claude Code's
// "Generating… 3m 16s" line. Rendered as an assistant-side bubble at the bottom of the chat
// while a turn is in flight, so the expert can tell "still working" apart from "stuck".
//
// The text describes the one thing actually happening (the turn request covers both
// understanding the answer and updating the graph in a single backend call), rather than
// faking separate phases the frontend can't observe.
import { useEffect, useState } from "react";

// After this long, add a reassurance line -- a real LLM call normally answers well before it.
const SLOW_AFTER_S = 10;

/** 3 -> "3s", 65 -> "1m 05s", 196 -> "3m 16s" */
export function formatElapsed(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${String(s % 60).padStart(2, "0")}s`;
}

export function ThinkingIndicator({ label = "正在理解你的回答，更新流程图…" }: { label?: string }) {
  // Timer starts when the bubble mounts, i.e. when the expert hits 发送.
  const [startedAt] = useState(() => Date.now());
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => setElapsed((Date.now() - startedAt) / 1000), 1000);
    return () => window.clearInterval(id);
  }, [startedAt]);

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        alignSelf: "flex-start", maxWidth: "82%", background: "#f8fafc", border: "1px dashed #cbd5e1",
        color: "#475569", borderRadius: 12, padding: "8px 12px", fontSize: 13, lineHeight: 1.5,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span
          aria-hidden
          style={{
            width: 12, height: 12, borderRadius: "50%", border: "2px solid #bfdbfe", borderTopColor: "#2a78d6",
            animation: "ewc-spin 0.8s linear infinite", flexShrink: 0,
          }}
        />
        <span>{label}</span>
        <span style={{ color: "#94a3b8", fontVariantNumeric: "tabular-nums" }}>{formatElapsed(elapsed)}</span>
      </div>
      {elapsed >= SLOW_AFTER_S && (
        <div style={{ fontSize: 11.5, color: "#94a3b8", marginTop: 4 }}>
          比平时慢一些，AI 还在处理，请稍等；如果失败，你刚才的回答会留在输入框里，可以直接重发。
        </div>
      )}
    </div>
  );
}
