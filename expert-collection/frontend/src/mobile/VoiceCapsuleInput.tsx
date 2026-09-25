// PRD 4.3.1 "语音口述转文字": tap mic -> record -> cancel(✕) / stop(■, fills the input,
// editable) / send(↑, sends immediately). Recognition now goes through the shared
// useVoiceDictation hook (IMPLEMENTATION_PLAN.md section 17.5): the backend relay to
// Qwen3-ASR-Flash-Realtime when it's configured, the browser's own SpeechRecognition
// otherwise. This component only owns the capsule UI.
import { useEffect } from "react";
import { useVoiceDictation } from "../hooks/useVoiceDictation";

interface Props {
  onTranscript: (text: string, mode: "fill" | "send") => void;
  disabled?: boolean;
  onRecordingChange?: (recording: boolean) => void;
}

export function VoiceCapsuleInput({ onTranscript, disabled, onRecordingChange }: Props) {
  const { state: dictState, liveText, error, start, stop } = useVoiceDictation();
  const recordingLike = dictState === "connecting" || dictState === "recording" || dictState === "finishing";
  const state = recordingLike ? "recording" : dictState === "unsupported" ? "unsupported" : "idle";
  const interim = liveText;

  useEffect(() => {
    onRecordingChange?.(recordingLike);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recordingLike]);

  function startRecognition() {
    if (disabled) return;
    void start();
  }

  async function stopRecognition(mode: "cancel" | "fill" | "send") {
    if (mode === "cancel") {
      await stop("cancel");
      return;
    }
    const text = await stop("keep");
    if (text) onTranscript(text, mode);
  }

  if (state === "recording") {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "10px 14px", background: "#eef4fc", borderRadius: 999 }}>
        <button
          aria-label="取消录音"
          onClick={() => stopRecognition("cancel")}
          style={circleBtn("#fff", "#94a3b8", "#667085")}
        >
          ✕
        </button>
        <div style={{ flex: 1, minWidth: 0, fontSize: 13, color: "#1f2937", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {interim || (dictState === "connecting" ? "正在连接……" : dictState === "finishing" ? "正在整理……" : "正在听……")}
        </div>
        <div style={{ display: "flex", gap: 4, alignItems: "flex-end", height: 18 }} aria-hidden>
          {[6, 12, 18, 10, 14].map((h, i) => (
            <span key={i} style={{ width: 3, height: h, background: "#2a78d6", borderRadius: 2, animation: "pulse 0.9s ease-in-out infinite", animationDelay: `${i * 0.1}s` }} />
          ))}
        </div>
        <button aria-label="停止并回填" onClick={() => stopRecognition("fill")} style={circleBtn("#fff", "#2a78d6", "#2a78d6")}>
          ■
        </button>
        <button aria-label="直接发送" onClick={() => stopRecognition("send")} style={circleBtn("#2a78d6", "#2a78d6", "#fff")}>
          ↑
        </button>
        <style>{`@keyframes pulse{0%,100%{transform:scaleY(0.4)}50%{transform:scaleY(1)}}`}</style>
      </div>
    );
  }

  return (
    <button
      aria-label="语音口述"
      disabled={disabled || state === "unsupported"}
      title={state === "unsupported" ? error ?? "当前浏览器不支持语音识别，请直接打字" : "点击开始语音口述"}
      onClick={startRecognition}
      style={{
        border: "none",
        background: state === "unsupported" ? "#f1f3f5" : "#2a78d6",
        color: state === "unsupported" ? "#a6acb4" : "#fff",
        width: 40,
        height: 40,
        borderRadius: "50%",
        flexShrink: 0,
        cursor: state === "unsupported" ? "default" : "pointer",
        fontSize: 16,
      }}
    >
      🎤
    </button>
  );
}

function circleBtn(bg: string, border: string, color: string): React.CSSProperties {
  return {
    width: 36,
    height: 36,
    borderRadius: "50%",
    border: `1.5px solid ${border}`,
    background: bg,
    color,
    fontSize: 14,
    flexShrink: 0,
    cursor: "pointer",
  };
}
