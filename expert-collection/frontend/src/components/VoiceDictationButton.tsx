// Desktop mic button for the chat input (IMPLEMENTATION_PLAN.md section 17.5). While
// recording, a strip above the input shows what's being recognized, then two icons decide
// where the transcript goes (PRD 4.3.1 / the voice-icon migration from Workforce):
// ① organize -- POST /api/voice/polish (app/speech_polish.py) cleans it up, then it's
//   appended to the draft box for the expert to check before sending.
// ② send -- skips the draft box, sent as its own turn immediately with the raw transcript.
import { useState } from "react";
import { api } from "../api/client";
import { useVoiceDictation } from "../hooks/useVoiceDictation";
import { OrganizeIntoInputIcon, RecognizeAndSendIcon } from "../voice/icons";

interface Props {
  disabled?: boolean;
  onFill: (text: string) => void;
  onSend: (text: string) => void;
}

export function VoiceDictationButton({ disabled, onFill, onSend }: Props) {
  const { state, liveText, error, start, stop } = useVoiceDictation();
  const active = state === "connecting" || state === "recording" || state === "finishing";
  const [polishing, setPolishing] = useState(false);

  async function finish(mode: "fill" | "send") {
    const text = await stop("keep");
    if (!text) return;
    if (mode === "send") {
      onSend(text);
      return;
    }
    setPolishing(true);
    try {
      const result = await api.polishSpeech(text);
      onFill(result.text);
    } catch {
      onFill(text);
    } finally {
      setPolishing(false);
    }
  }

  return (
    <>
      {(active || error || polishing) && (
        <div
          style={{
            position: "absolute", left: 16, right: 16, bottom: "100%", marginBottom: 6,
            background: error && !active ? "#fef2f2" : "#eef4fc", border: `1px solid ${error && !active ? "#fecaca" : "#bfd4f2"}`,
            borderRadius: 8, padding: "8px 10px", fontSize: 12.5, display: "flex", alignItems: "center", gap: 8,
          }}
        >
          <div style={{ flex: 1, minWidth: 0, color: error && !active ? "#991b1b" : "#1f2937", maxHeight: 96, overflowY: "auto" }}>
            {polishing
              ? "AI 正在整理…"
              : active
                ? liveText || (state === "connecting" ? "正在连接语音识别……" : state === "finishing" ? "正在整理最后一句……" : "正在听，您可以一次把整个过程讲完……")
                : error}
          </div>
          {active && !polishing ? (
            <>
              <button onClick={() => stop("cancel")} style={stripBtn(false)}>取消</button>
              <button
                aria-label="整理后填入输入框"
                title="整理后填入输入框"
                disabled={state === "finishing"}
                onClick={() => finish("fill")}
                style={iconBtn("#fff", "#2a78d6", "#2a78d6")}
              >
                <OrganizeIntoInputIcon size={16} />
              </button>
              <button
                aria-label="识别后直接发送"
                title="识别后直接发送"
                disabled={state === "finishing"}
                onClick={() => finish("send")}
                style={iconBtn("#2a78d6", "#2a78d6", "#fff")}
              >
                <RecognizeAndSendIcon size={16} />
              </button>
            </>
          ) : null}
        </div>
      )}
      <button
        aria-label="语音输入"
        title="语音输入：说完选择整理填入或直接发送"
        disabled={disabled || active}
        onClick={start}
        style={{
          border: "1px solid #d0d5dd", borderRadius: 8, width: 40, flexShrink: 0,
          background: active ? "#eef4fc" : "#fff", cursor: disabled || active ? "default" : "pointer", fontSize: 16,
        }}
      >
        🎤
      </button>
    </>
  );
}

function stripBtn(primary: boolean) {
  return {
    border: primary ? "none" : "1px solid #d0d5dd", borderRadius: 6, padding: "4px 12px", fontSize: 12,
    background: primary ? "#2a78d6" : "#fff", color: primary ? "#fff" : "#475569", cursor: "pointer", flexShrink: 0,
  } as const;
}

function iconBtn(bg: string, border: string, color: string) {
  return {
    width: 28, height: 28, borderRadius: "50%", border: `1.5px solid ${border}`, background: bg, color,
    display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", flexShrink: 0,
  } as const;
}
