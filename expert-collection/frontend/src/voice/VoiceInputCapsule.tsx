// Shared voice input control for the expert conversation (desktop ChatPanel + mobile
// MobileChatPage) -- ports Workforce's two voice features (docs/qwen-realtime-voice-setup.md,
// web-demo/README.md) into the expert session:
//
// - "语音录入" (speech-to-text dictation) -- tap the mic, speak a long answer in one go, then
//   choose how it lands:
//     ① organize icon -- the raw transcript is cleaned up by an LLM pass (POST
//        /api/voice/polish, wired to the `mobile_speech_polish` slot) and fills the input box,
//        still editable before sending.
//     ② send icon -- the raw transcript skips the input box and is sent as a turn immediately.
//     ✕ -- cancel, discard whatever was captured.
// - "语音对话" (realtime voice dialog) -- the larger ③ button opens RealtimeVoiceDialog, a
//   hands-free continuous back-and-forth modeled on Workforce's ChatGPT-style voice mode
//   (web-demo/static/app.js's connection-lifecycle rules: fail fast instead of hanging on
//   "connecting...", auto end an idle session).
//
// Recognition backend: PRD 6.2 / Workforce's target is Qwen Realtime (`docs/
// qwen-realtime-voice-setup.md`), reachable via the `voice` settings block
// (workspace_id/realtime_model) that app/settings.py already scaffolds. This sandbox has no
// reachable dashscope endpoint or verified wire protocol for it to test against, so both this
// capsule and RealtimeVoiceDialog run on the browser's own SpeechRecognition/SpeechSynthesis
// APIs instead -- real, working, needs no server or API key, wherever the browser supports it
// (Chrome/Edge; not Firefox/desktop Safari). Only `startRecognition`/`stopRecognition` here and
// the connection setup in useRealtimeVoiceDialog.ts would need to change to swap in the real
// Qwen Realtime link; every caller-facing prop stays the same.
import { useEffect, useRef, useState } from "react";
import type { ConversationTurn } from "../api/types";
import { api } from "../api/client";
import { OrganizeIntoInputIcon, RecognizeAndSendIcon, RealtimeVoiceIcon } from "./icons";
import { RealtimeVoiceDialog } from "./RealtimeVoiceDialog";

type RecognitionState = "idle" | "recording" | "unsupported";

// Minimal shape of the non-standard SpeechRecognition API -- no official TS lib types ship
// for it, so we declare just what we use rather than pulling in a whole ambient-types package.
interface MinimalSpeechRecognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onstart: (() => void) | null;
  onresult: ((event: any) => void) | null;
  onerror: ((event: any) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

export function getSpeechRecognitionCtor(): (new () => MinimalSpeechRecognition) | null {
  const w = window as any;
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

interface Props {
  onTranscript: (text: string, mode: "fill" | "send") => void;
  disabled?: boolean;
  onRecordingChange?: (recording: boolean) => void;
  turns: ConversationTurn[];
  sending: boolean;
}

export function VoiceInputCapsule({ onTranscript, disabled, onRecordingChange, turns, sending }: Props) {
  const Ctor = useRef(getSpeechRecognitionCtor()).current;
  const [state, setState] = useState<RecognitionState>(Ctor ? "idle" : "unsupported");
  const [interim, setInterim] = useState("");
  const [polishing, setPolishing] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
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

  async function stopRecognition(mode: "cancel" | "fill" | "send") {
    recognitionRef.current?.stop();
    setState("idle");
    onRecordingChange?.(false);
    const text = (finalTextRef.current + interim).trim();
    setInterim("");
    if (mode === "cancel" || !text) return;

    if (mode === "send") {
      onTranscript(text, "send");
      return;
    }

    // mode === "fill": icon ① -- let the LLM organize it before it lands in the input box.
    // Never block on this: any failure (offline, service not configured) falls back to the
    // raw transcript rather than losing what the expert just said.
    setPolishing(true);
    try {
      const result = await api.polishSpeech(text);
      onTranscript(result.text, "fill");
    } catch {
      onTranscript(text, "fill");
    } finally {
      setPolishing(false);
    }
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      {state === "recording" ? (
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", background: "#eef4fc", borderRadius: 999, flex: 1, minWidth: 0 }}>
          <button aria-label="取消录音" onClick={() => stopRecognition("cancel")} style={circleBtn("#fff", "#94a3b8", "#667085")}>
            ✕
          </button>
          <div style={{ flex: 1, minWidth: 0, fontSize: 13, color: "#1f2937", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {polishing ? "AI 正在整理…" : interim || finalTextRef.current || "正在听……"}
          </div>
          {!polishing && (
            <div style={{ display: "flex", gap: 4, alignItems: "flex-end", height: 18 }} aria-hidden>
              {[6, 12, 18, 10, 14].map((h, i) => (
                <span key={i} style={{ width: 3, height: h, background: "#2a78d6", borderRadius: 2, animation: "voice-pulse 0.9s ease-in-out infinite", animationDelay: `${i * 0.1}s` }} />
              ))}
            </div>
          )}
          <button
            aria-label="整理后填入输入框"
            title="整理后填入输入框"
            onClick={() => stopRecognition("fill")}
            disabled={polishing}
            style={circleBtn("#fff", "#2a78d6", "#2a78d6")}
          >
            <OrganizeIntoInputIcon size={17} />
          </button>
          <button
            aria-label="识别后直接发送"
            title="识别后直接发送"
            onClick={() => stopRecognition("send")}
            disabled={polishing}
            style={circleBtn("#2a78d6", "#2a78d6", "#fff")}
          >
            <RecognizeAndSendIcon size={17} />
          </button>
          <style>{`@keyframes voice-pulse{0%,100%{transform:scaleY(0.4)}50%{transform:scaleY(1)}}`}</style>
        </div>
      ) : (
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
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 16,
          }}
        >
          🎤
        </button>
      )}

      <button
        aria-label="实时语音会话"
        title={state === "unsupported" ? "当前浏览器不支持语音识别，请直接打字" : "开始实时语音会话"}
        disabled={disabled || state === "unsupported"}
        onClick={() => setDialogOpen(true)}
        style={{
          border: "none",
          background: state === "unsupported" ? "#f1f3f5" : "#eef4fc",
          color: state === "unsupported" ? "#a6acb4" : "#2a78d6",
          width: 44,
          height: 44,
          borderRadius: "50%",
          flexShrink: 0,
          cursor: state === "unsupported" ? "default" : "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <RealtimeVoiceIcon size={26} />
      </button>

      {dialogOpen && (
        <RealtimeVoiceDialog
          turns={turns}
          sending={sending}
          onSend={(text) => onTranscript(text, "send")}
          onClose={() => setDialogOpen(false)}
        />
      )}
    </div>
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
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  };
}
