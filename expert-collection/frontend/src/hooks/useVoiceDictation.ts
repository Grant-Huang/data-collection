// Voice-to-text for the expert input box (IMPLEMENTATION_PLAN.md section 17.5), shared by the
// desktop ChatPanel and the mobile VoiceCapsuleInput.
//
// Primary path: mic -> AudioWorklet -> 16 kHz PCM16 -> backend relay (/api/voice/asr) ->
// Qwen3-ASR-Flash-Realtime in server-VAD mode, which segments a long narration into
// sentences on its own. Fallback when the relay isn't configured: the browser's own
// SpeechRecognition (server-based per MDN; in Chrome that service may be unreachable on
// mainland networks, so it's only a fallback).
//
// Output is exactly one text: what the recognizer heard. It is not polished here -- the
// agent's own reply carries its interpretation (section 17 decision 5), and this raw text is
// also what gets stored as `raw_transcript` next to the expert-edited message.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, wsUrl } from "../api/client";

export type DictationState = "idle" | "connecting" | "recording" | "finishing" | "unsupported";

// --- audio helpers (same math as web-demo/static/app.js) ---
function downsampleTo16k(input: Float32Array, inputRate: number): Float32Array {
  if (inputRate === 16000) return input;
  const ratio = inputRate / 16000;
  const out = new Float32Array(Math.floor(input.length / ratio));
  for (let i = 0; i < out.length; i++) {
    const src = i * ratio;
    const i0 = Math.floor(src);
    const i1 = Math.min(i0 + 1, input.length - 1);
    const frac = src - i0;
    out[i] = input[i0] * (1 - frac) + input[i1] * frac;
  }
  return out;
}

function pcm16Base64(f32: Float32Array): string {
  const pcm = new Int16Array(f32.length);
  for (let i = 0; i < f32.length; i++) {
    const s = Math.max(-1, Math.min(1, f32[i]));
    pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  const bytes = new Uint8Array(pcm.buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

function getBrowserRecognizer(): (new () => any) | null {
  const w = window as any;
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

// Cached across hook instances: whether the backend relay has a key configured.
let relayStatus: Promise<boolean> | null = null;
function relayConfigured(): Promise<boolean> {
  if (!relayStatus) relayStatus = api.voiceStatus().then((s) => s.configured).catch(() => false);
  return relayStatus;
}

export function useVoiceDictation() {
  const [state, setState] = useState<DictationState>("idle");
  const [liveText, setLiveText] = useState("");
  const [error, setError] = useState<string | null>(null);

  const finals = useRef<string[]>([]);
  const partial = useRef("");
  const ws = useRef<WebSocket | null>(null);
  const audioCtx = useRef<AudioContext | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const recognizer = useRef<any>(null);
  const finished = useRef<(() => void) | null>(null);

  const refreshLive = () => setLiveText(finals.current.join("") + partial.current);

  const releaseAudio = () => {
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
    audioCtx.current?.close().catch(() => {});
    audioCtx.current = null;
  };

  const teardown = useCallback(() => {
    releaseAudio();
    ws.current?.close();
    ws.current = null;
    recognizer.current?.abort?.();
    recognizer.current = null;
  }, []);

  useEffect(() => teardown, [teardown]);

  const startBrowser = () => {
    const Ctor = getBrowserRecognizer();
    if (!Ctor) {
      setState("unsupported");
      setError("语音识别服务未配置，当前浏览器也不支持语音识别，请直接打字");
      return;
    }
    const r = new Ctor();
    r.lang = "zh-CN";
    r.continuous = true;
    r.interimResults = true;
    r.onresult = (event: any) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const res = event.results[i];
        if (res.isFinal) finals.current.push(res[0].transcript);
        else interim += res[0].transcript;
      }
      partial.current = interim;
      refreshLive();
    };
    r.onerror = (e: any) => setError(`浏览器语音识别出错：${e?.error ?? "未知错误"}`);
    r.onend = () => finished.current?.();
    recognizer.current = r;
    r.start();
    setState("recording");
  };

  const startRelay = async () => {
    const socket = new WebSocket(wsUrl("/api/voice/asr"));
    ws.current = socket;
    const pending: string[] = []; // audio captured before the socket opened
    socket.onopen = () => {
      pending.splice(0).forEach((a) => socket.send(JSON.stringify({ type: "input_audio_buffer.append", audio: a })));
    };
    socket.onmessage = (ev) => {
      let msg: any;
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (msg.type === "conversation.item.input_audio_transcription.text") {
        partial.current = (msg.text ?? "") + (msg.stash ?? "");
        refreshLive();
      } else if (msg.type === "conversation.item.input_audio_transcription.completed") {
        finals.current.push(msg.transcript ?? "");
        partial.current = "";
        refreshLive();
      } else if (msg.type === "session.finished") {
        finished.current?.();
      } else if (msg.type === "relay.error" || msg.type === "error") {
        setError(msg.message ?? msg.error?.message ?? "语音识别出错");
      }
    };
    socket.onclose = () => finished.current?.();

    stream.current = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
    const ctx = new AudioContext();
    audioCtx.current = ctx;
    await ctx.audioWorklet.addModule("/mic-capture-worklet.js");
    const node = new AudioWorkletNode(ctx, "mic-capture");
    node.port.onmessage = (ev) => {
      const audio = pcm16Base64(downsampleTo16k(ev.data as Float32Array, ctx.sampleRate));
      if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "input_audio_buffer.append", audio }));
      else if (socket.readyState === WebSocket.CONNECTING) pending.push(audio);
    };
    ctx.createMediaStreamSource(stream.current).connect(node);
    setState("recording");
  };

  const start = useCallback(async () => {
    if (state !== "idle" && state !== "unsupported") return;
    setError(null);
    finals.current = [];
    partial.current = "";
    setLiveText("");
    setState("connecting");
    try {
      if (await relayConfigured()) await startRelay();
      else startBrowser();
    } catch (e) {
      teardown();
      setState("idle");
      setError(`无法开始录音：${e instanceof Error ? e.message : String(e)}`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, teardown]);

  // Stops listening. "keep" waits (briefly) for the recognizer to flush the last sentence and
  // resolves with the full transcript; "cancel" discards everything.
  const stop = useCallback(async (mode: "keep" | "cancel"): Promise<string> => {
    if (mode === "cancel") {
      teardown();
      setState("idle");
      setLiveText("");
      return "";
    }
    setState("finishing");
    releaseAudio(); // stop capturing now; what was already sent still gets transcribed
    await new Promise<void>((resolve) => {
      const timer = setTimeout(resolve, 4000);
      finished.current = () => {
        clearTimeout(timer);
        resolve();
      };
      if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify({ type: "session.finish" }));
      else if (recognizer.current) recognizer.current.stop();
      else resolve();
    });
    finished.current = null;
    const text = (finals.current.join("") + partial.current).trim();
    teardown();
    setState("idle");
    setLiveText("");
    return text;
  }, [teardown]);

  return { state, liveText, error, start, stop };
}
