// Drives icon ③'s "实时语音会话" overlay: a hands-free loop of listen -> submit turn -> speak
// the assistant's reply -> listen again, modeled on Workforce's ChatGPT-style voice mode
// (web-demo/static/app.js) and its three connection-lifecycle rules from
// docs/qwen-realtime-voice-setup.md / web-demo/README.md ("连接生命周期设计"):
//   (a) a stuck "connecting" state must fail loudly, not hang forever -- CONNECT_TIMEOUT_MS.
//   (b) an established session is never torn down on its own mid-conversation.
//   (c) a long-idle session (nobody speaking) auto-ends -- IDLE_TIMEOUT_MS, same 5 minutes
//       Workforce settled on after real-device testing.
//
// Recognition/TTS backend: this runs on the browser's own SpeechRecognition + SpeechSynthesis,
// not the real /api/voice/asr relay to Qwen3-ASR-Flash-Realtime that
// useVoiceDictation.ts/VoiceDictationButton.tsx/VoiceCapsuleInput.tsx use for one-shot
// dictation (icons ①/②). That relay's session is meant to be finished once per dictation
// ("session.finish" in useVoiceDictation.ts's `stop`); this dialog instead needs a session
// kept open across many turns, judging its own turn boundaries locally so it can react
// immediately (submit + speak back) rather than waiting on a round trip through the backend.
// Rebuilding icon ③ on a long-lived relay session is the natural next step once the relay
// exposes something for that; today, swapping it in would only touch `beginListeningCycle`/
// `speak` below.
//
// Every mutable flag read inside a SpeechRecognition/SpeechSynthesis callback is kept in a
// ref, not a plain closure over React state -- those callbacks fire from browser-internal
// event loops, not React's render cycle, so a captured `useState` value would go stale the
// moment the component re-renders for any other reason.
import { useCallback, useEffect, useRef, useState, type MutableRefObject } from "react";
import type { ConversationTurn } from "../api/types";
import { getSpeechRecognitionCtor } from "./browserSpeech";

export type DialogPhase = "connecting" | "listening" | "thinking" | "speaking" | "error" | "unsupported";

const CONNECT_TIMEOUT_MS = 8_000;
const IDLE_TIMEOUT_MS = 5 * 60_000;
// If a turn we submitted hasn't produced a new assistant reply within this long, resume
// listening anyway instead of hanging in "thinking" forever (mirrors the honesty rule in
// llm_client.py/app.js: a slow backend degrades the experience, it never silently freezes it).
const REPLY_WAIT_TIMEOUT_MS = 20_000;

interface Options {
  turns: ConversationTurn[];
  sending: boolean;
  onSend: (text: string) => void;
}

export function useRealtimeVoiceDialog({ turns, sending, onSend }: Options) {
  const Ctor = useRef(getSpeechRecognitionCtor()).current;
  const [phase, setPhase] = useState<DialogPhase>(Ctor ? "connecting" : "unsupported");
  const [liveText, setLiveText] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const recognitionRef = useRef<any>(null);
  const awaitingReplyRef = useRef(false);
  const closedRef = useRef(false);
  const turnsRef = useRef(turns);
  const sendingRef = useRef(sending);
  const turnsAtSendRef = useRef(0);
  const connectTimerRef = useRef<number | null>(null);
  const idleTimerRef = useRef<number | null>(null);
  const replyWaitTimerRef = useRef<number | null>(null);

  useEffect(() => {
    turnsRef.current = turns;
  }, [turns]);
  useEffect(() => {
    sendingRef.current = sending;
  }, [sending]);

  const clearTimer = (ref: MutableRefObject<number | null>) => {
    if (ref.current != null) window.clearTimeout(ref.current);
    ref.current = null;
  };

  const armIdleTimer = useCallback(() => {
    clearTimer(idleTimerRef);
    idleTimerRef.current = window.setTimeout(() => {
      setErrorMessage("长时间没有说话，已自动结束语音会话");
      setPhase("error");
      teardown();
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, IDLE_TIMEOUT_MS);
  }, []);

  function teardown() {
    clearTimer(connectTimerRef);
    clearTimer(idleTimerRef);
    clearTimer(replyWaitTimerRef);
    recognitionRef.current?.abort?.();
    recognitionRef.current = null;
    window.speechSynthesis?.cancel();
  }

  const beginListeningCycle = useCallback(() => {
    if (!Ctor || closedRef.current) return;
    const recognition = new Ctor();
    recognition.lang = "zh-CN";
    recognition.continuous = true;
    recognition.interimResults = true;

    recognition.onstart = () => {
      clearTimer(connectTimerRef);
      if (closedRef.current) return;
      setPhase("listening");
      setErrorMessage(null);
      armIdleTimer();
    };

    recognition.onresult = (event: any) => {
      armIdleTimer();
      let interimText = "";
      let finalText = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) finalText += result[0].transcript;
        else interimText += result[0].transcript;
      }
      setLiveText(interimText);
      const trimmed = finalText.trim();
      if (trimmed) {
        awaitingReplyRef.current = true;
        turnsAtSendRef.current = turnsRef.current.length;
        setLiveText("");
        setPhase("thinking");
        recognition.stop();
        onSend(trimmed);
        replyWaitTimerRef.current = window.setTimeout(() => {
          if (awaitingReplyRef.current) {
            awaitingReplyRef.current = false;
            beginListeningCycle();
          }
        }, REPLY_WAIT_TIMEOUT_MS);
      }
    };

    recognition.onerror = (event: any) => {
      if (event.error === "no-speech" || event.error === "aborted") return; // benign
      clearTimer(connectTimerRef);
      setErrorMessage(
        event.error === "not-allowed"
          ? "麦克风权限被拒绝，请在浏览器设置里允许访问后重试"
          : `语音识别出错：${event.error}`,
      );
      setPhase("error");
      teardown();
    };

    recognition.onend = () => {
      // A browser can end recognition on its own after a stretch of silence even with
      // continuous=true. Only auto-restart if we're still supposed to be listening --
      // not paused because we're about to submit a turn, not closed, not already erroring.
      if (!closedRef.current && !awaitingReplyRef.current) {
        try {
          recognition.start();
        } catch {
          /* already starting */
        }
      }
    };

    recognitionRef.current = recognition;
    try {
      recognition.start();
    } catch {
      setErrorMessage("无法启动麦克风");
      setPhase("error");
    }
  }, [Ctor, armIdleTimer, onSend]);

  const speak = useCallback((text: string) => {
    if (!("speechSynthesis" in window) || closedRef.current) {
      beginListeningCycle();
      return;
    }
    setPhase("speaking");
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "zh-CN";
    utterance.onend = () => {
      if (!closedRef.current) beginListeningCycle();
    };
    utterance.onerror = () => {
      if (!closedRef.current) beginListeningCycle();
    };
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
  }, [beginListeningCycle]);

  // Watches for the assistant's reply landing in `turns` after we submitted one via onSend.
  useEffect(() => {
    if (!awaitingReplyRef.current) return;
    if (sending) return; // request still in flight
    if (turns.length <= turnsAtSendRef.current) return; // no new turn yet
    awaitingReplyRef.current = false;
    clearTimer(replyWaitTimerRef);
    const latest = turns[turns.length - 1];
    if (latest && latest.role === "assistant" && latest.text.trim()) {
      speak(latest.text);
    } else {
      beginListeningCycle();
    }
  }, [turns, sending, speak, beginListeningCycle]);

  // Kick off the very first listening cycle when the dialog mounts.
  useEffect(() => {
    closedRef.current = false;
    if (!Ctor) {
      setPhase("unsupported");
      return;
    }
    connectTimerRef.current = window.setTimeout(() => {
      setErrorMessage("连接超时，请重试");
      setPhase("error");
      teardown();
    }, CONNECT_TIMEOUT_MS);
    beginListeningCycle();
    return () => {
      closedRef.current = true;
      teardown();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const retry = useCallback(() => {
    setErrorMessage(null);
    closedRef.current = false;
    connectTimerRef.current = window.setTimeout(() => {
      setErrorMessage("连接超时，请重试");
      setPhase("error");
      teardown();
    }, CONNECT_TIMEOUT_MS);
    beginListeningCycle();
  }, [beginListeningCycle]);

  const close = useCallback(() => {
    closedRef.current = true;
    teardown();
  }, []);

  return { phase, liveText, errorMessage, retry, close };
}
