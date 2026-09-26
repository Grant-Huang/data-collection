// Minimal shape of the non-standard SpeechRecognition API -- no official TS lib types ship
// for it, so we declare just what we use rather than pulling in a whole ambient-types package.
// Used by useRealtimeVoiceDialog.ts's continuous listen/reply loop (icon ③): unlike the
// one-shot dictation in VoiceCapsuleInput/VoiceDictationButton (which goes through the shared
// useVoiceDictation hook and its Qwen relay), the realtime dialog always runs on the browser's
// own recognizer -- see useRealtimeVoiceDialog.ts's top comment for why.
export interface MinimalSpeechRecognition {
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
