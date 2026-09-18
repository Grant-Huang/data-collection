// PRD 4.3.1 "语音口述转文字": tap mic -> record -> cancel(✕) / stop(■, fills the input,
// editable) / send(↑, sends immediately). PRD 6.2 specifies this should run over the same
// Realtime ASR link web-demo/server.py already proxies to Qwen (`QWEN_API_KEY` +
// `conversation.item.input_audio_transcription.completed`) -- but this sandbox has no
// QWEN_API_KEY and no reachable dashscope endpoint (see IMPLEMENTATION_PLAN.md's Mock Guide
// Service precedent: same honesty rule applies here). Real, working substitute for now:
// the browser's own SpeechRecognition API, which needs no server or API key and actually
// works end-to-end wherever it's supported (Chrome/Edge on Android; not Firefox/desktop
// Safari). The three-button/waveform UI and the transcript hand-off are real product
// behavior, not a mock -- only the recognition backend differs from the PRD's target. When a
// real Qwen Realtime link is wired up, only `startRecognition`/`stopRecognition` below need
// to change; the component's public surface (onTranscript) stays the same.
import { useEffect, useRef, useState } from "react";

type RecognitionState = "idle" | "recording" | "unsupported";

// Minimal shape of the non-standard SpeechRecognition API -- no official TS lib types ship
// for it, so we declare just what we use rather than pulling in a whole ambient-types package.
interface MinimalSpeechRecognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: any) => void) | null;
  onerror: ((event: any) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

function getSpeechRecognitionCtor(): (new () => MinimalSpeechRecognition) | null {
  const w = window as any;
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

interface Props {
  onTranscript: (text: string, mode: "fill" | "send") => void;
  disabled?: boolean;
  onRecordingChange?: (recording: boolean) => void;
}

export function VoiceCapsuleInput({ onTranscript, disabled, onRecordingChange }: Props) {
  const Ctor = useRef(getSpeechRecognitionCtor()).current;
  const [state, setState] = useState<RecognitionState>(Ctor ? "idle" : "unsupported");
  const [interim, setInterim] = useState("");
  const recognitionRef = useRef<MinimalSpeechRecognition | null>(null);
  const finalTextRef = useRef("");

  useEffect(() => () => recognitionRef.current?.abort(), []);

  function startRecognition() {
    if (!Ctor || disabled) return;
    const recognition = new Ctor();
    recognition.lang = "zh-CN";
    recognition.continuous = true;
    recognition.interimResults = true;
    finalTextRef.current = "";
    setInterim("");
    recognition.onresult = (event: any) => {
      let interimText = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) finalTextRef.current += result[0].transcript;
        else interimText += result[0].transcript;
      }
      setInterim(interimText);
    };
    recognition.onerror = () => {
      setState("idle");
      onRecordingChange?.(false);
    };
    recognition.onend = () => {
      setState("idle");
      onRecordingChange?.(false);
    };
    recognitionRef.current = recognition;
    recognition.start();
    setState("recording");
    onRecordingChange?.(true);
  }

  function stopRecognition(mode: "cancel" | "fill" | "send") {
    recognitionRef.current?.stop();
    setState("idle");
    onRecordingChange?.(false);
    const text = (finalTextRef.current + interim).trim();
    setInterim("");
    if (mode !== "cancel" && text) onTranscript(text, mode === "send" ? "send" : "fill");
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
          {interim || finalTextRef.current || "正在听……"}
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
      title={state === "unsupported" ? "当前浏览器不支持语音识别，请直接打字" : "点击开始语音口述"}
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
