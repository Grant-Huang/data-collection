// Full-screen overlay for icon ③, "实时语音会话" -- a ChatGPT-voice-mode-style hands-free
// conversation: the expert just talks, each pause becomes a turn sent into the session, and
// the assistant's reply is read back out loud before listening resumes. See
// useRealtimeVoiceDialog.ts's top comment for the state machine and the honest note on which
// speech backend this actually runs on in this sandbox.
import type { ConversationTurn } from "../api/types";
import { RealtimeVoiceIcon } from "./icons";
import { useRealtimeVoiceDialog } from "./useRealtimeVoiceDialog";

interface Props {
  turns: ConversationTurn[];
  sending: boolean;
  onSend: (text: string) => void;
  onClose: () => void;
}

const PHASE_LABEL: Record<string, string> = {
  connecting: "正在连接麦克风…",
  listening: "在听你说……",
  thinking: "正在处理…",
  speaking: "助手正在回复……",
  error: "出错了",
  unsupported: "当前浏览器不支持语音识别",
};

export function RealtimeVoiceDialog({ turns, sending, onSend, onClose }: Props) {
  const { phase, liveText, errorMessage, retry, close } = useRealtimeVoiceDialog({ turns, sending, onSend });
  const lastAssistantTurn = [...turns].reverse().find((t) => t.role === "assistant");

  function handleClose() {
    close();
    onClose();
  }

  return (
    <div
      role="dialog"
      aria-label="实时语音会话"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(15, 23, 42, 0.92)",
        zIndex: 1000,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        color: "#fff",
        padding: 24,
      }}
    >
      <button
        aria-label="关闭实时语音会话"
        onClick={handleClose}
        style={{
          position: "absolute",
          top: 20,
          right: 20,
          width: 40,
          height: 40,
          borderRadius: "50%",
          border: "1px solid rgba(255,255,255,0.3)",
          background: "rgba(255,255,255,0.08)",
          color: "#fff",
          fontSize: 18,
          cursor: "pointer",
        }}
      >
        ✕
      </button>

      <div
        style={{
          width: 140,
          height: 140,
          borderRadius: "50%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background:
            phase === "listening"
              ? "radial-gradient(circle, rgba(42,120,214,0.35), transparent 70%)"
              : phase === "speaking"
                ? "radial-gradient(circle, rgba(12,163,12,0.35), transparent 70%)"
                : "radial-gradient(circle, rgba(148,163,184,0.25), transparent 70%)",
          transition: "background 0.3s",
        }}
      >
        <RealtimeVoiceIcon size={72} active={phase === "listening" || phase === "speaking"} />
      </div>

      <div style={{ marginTop: 24, fontSize: 15, fontWeight: 600 }}>{PHASE_LABEL[phase] ?? phase}</div>

      <div style={{ marginTop: 12, minHeight: 44, maxWidth: 480, textAlign: "center", fontSize: 13.5, color: "rgba(255,255,255,0.75)", padding: "0 16px" }}>
        {phase === "error" ? (
          errorMessage ?? "出现了未知错误"
        ) : phase === "listening" ? (
          liveText || "（说话试试，说完停顿一下就会自动处理）"
        ) : phase === "speaking" && lastAssistantTurn ? (
          lastAssistantTurn.text
        ) : phase === "unsupported" ? (
          "请使用 Chrome / Edge 等支持语音识别的浏览器，或直接打字输入"
        ) : (
          ""
        )}
      </div>

      {phase === "error" && (
        <button
          onClick={retry}
          style={{
            marginTop: 18,
            border: "none",
            borderRadius: 8,
            padding: "8px 20px",
            background: "#2a78d6",
            color: "#fff",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          重试
        </button>
      )}

      <button
        onClick={handleClose}
        style={{
          marginTop: 28,
          border: "1px solid rgba(255,255,255,0.3)",
          borderRadius: 999,
          padding: "8px 22px",
          background: "transparent",
          color: "#fff",
          fontSize: 13,
          cursor: "pointer",
        }}
      >
        结束语音会话
      </button>
    </div>
  );
}
