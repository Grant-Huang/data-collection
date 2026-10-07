// PRD 4.2/4.3: mobile session page = default home. Minimal top bar (hamburger + name + info),
// message list identical to desktop, capsule input row with mic (PRD 4.3.1).
import { useRef, useState } from "react";
import type { WorkflowRecord } from "../api/types";
import { MessageList } from "../components/MessageList";
import { thinkingLabel } from "../components/ThinkingIndicator";
import { mergeChipIntoDraft } from "../utils/chips";
import { VoiceCapsuleInput } from "./VoiceCapsuleInput";
import { RealtimeVoiceDialog } from "../voice/RealtimeVoiceDialog";
import { RealtimeVoiceIcon } from "../voice/icons";

interface Props {
  active: WorkflowRecord | null;
  sending: boolean;
  // May resolve to false when the turn failed -- the text then goes back into the input box.
  onSend: (text: string, rawTranscript?: string) => void | Promise<boolean | void>;
  onOpenDrawer: () => void;
  onToggleProgress: () => void;
  progressOpen: boolean;
  recordingChanged: (recording: boolean) => void;
  // 「确认并提交」 and the error line sit in the column right above the input row (B7): as
  // absolutely-positioned overlays they covered the newest message and the chips under it.
  onConfirm?: () => void;
  error?: string | null;
}

export function MobileChatPage({ active, sending, onSend, onOpenDrawer, onToggleProgress, progressOpen, recordingChanged, onConfirm, error }: Props) {
  const [draft, setDraft] = useState("");
  // Raw recognizer output dictated into the current draft (see ChatPanel).
  const [rawPieces, setRawPieces] = useState<string[]>([]);
  // While recording, the voice capsule takes the whole input row -- next to the text input it
  // overflowed a 390px-wide screen and pushed its stop/send buttons off-screen.
  const [recording, setRecording] = useState(false);
  const [voiceDialogOpen, setVoiceDialogOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const confirmed = active?.status === "expert_confirmed";
  // The message currently being processed -- decides what the "AI is working" line says.
  const [lastSent, setLastSent] = useState<string | null>(null);
  const nextQuestion = active?.unresolved[0] ?? null;

  // Same rule as desktop: chips prefill an editable draft (appending to anything the expert
  // already typed), never auto-send. Multi-select is handled inside the shared QuickReplies.
  function handleChip(pick: string) {
    setDraft((prev) => mergeChipIntoDraft(prev, pick, nextQuestion?.chips ?? []));
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  function handleSend(text?: string, raw?: string) {
    const value = (text ?? draft).trim();
    if (!value || sending || confirmed) return;
    setDraft("");
    const rawAll = [...rawPieces, ...(raw ? [raw] : [])].join("");
    setRawPieces([]);
    setLastSent(value);
    void Promise.resolve(onSend(value, rawAll || undefined)).then((ok) => {
      if (ok === false) setDraft((current) => current || value);
    });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "#fff" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", borderBottom: "1px solid #e5e7eb" }}>
        <button
          aria-label="历史流程"
          onClick={onOpenDrawer}
          style={{ border: "none", background: "none", fontSize: 20, padding: 4, minWidth: 44, minHeight: 44 }}
        >
          ☰
        </button>
        <div style={{ flex: 1, minWidth: 0, textAlign: "center" }}>
          <div style={{ fontWeight: 700, fontSize: 14, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {active?.name ?? "新的流程"}
          </div>
        </div>
        <button
          aria-label="采集进度"
          onClick={onToggleProgress}
          style={{ border: "none", background: "none", fontSize: 18, padding: 4, minWidth: 44, minHeight: 44 }}
        >
          ⓘ
        </button>
      </div>

      {progressOpen && active && (
        <div style={{ padding: "8px 14px", borderBottom: "1px solid #e5e7eb", background: "#f8fafc", fontSize: 12, color: "#475569" }}>
          完成度 {Math.round(active.completion.score * 100)}% · 当前阶段 {active.stage}
          {active.completion.ready_for_confirmation && active.status !== "expert_confirmed" && " · 可以确认提交了"}
        </div>
      )}
      {!progressOpen && active && (
        <div style={{ height: 3, background: "#e5e7eb" }}>
          <div style={{ height: "100%", width: `${Math.round(active.completion.score * 100)}%`, background: "#2a78d6", transition: "width 0.3s" }} />
        </div>
      )}

      {active ? (
        <MessageList
          turns={active.turns}
          graph={active.graph}
          activeQuestion={confirmed ? null : nextQuestion}
          onChipPick={handleChip}
          sending={sending}
          sendingLabel={thinkingLabel(active.stage, lastSent)}
        />
      ) : (
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "#667085", fontSize: 13, padding: 24, textAlign: "center" }}>
          点击左上角「☰」新建一个流程开始讲述
        </div>
      )}

      {active?.stage === "review_narrative" && !confirmed && active.turns.some((t) => t.role === "expert") && (
        <div className="narrative-done-bar" style={{ padding: "8px 14px 0" }}>
          <span>讲完了再点 →</span>
          <button disabled={sending} onClick={() => handleSend("讲完了")}>✓ 讲完了，开始整理</button>
        </div>
      )}

      {error && (
        <div role="alert" style={{ margin: "8px 14px 0", background: "#fef2f2", border: "1px solid #fecaca", color: "#991b1b", borderRadius: 8, padding: "8px 12px", fontSize: 12 }}>
          {error}
        </div>
      )}

      {onConfirm && active?.completion.ready_for_confirmation && !confirmed && (
        <div style={{ padding: "8px 14px 0" }}>
          <button
            onClick={onConfirm}
            disabled={sending}
            style={{ width: "100%", border: "none", borderRadius: 8, padding: "12px 0", background: "#0ca30c", color: "#fff", fontWeight: 600, minHeight: 44 }}
          >
            确认并提交
          </button>
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 14px", borderTop: "1px solid #e5e7eb" }}>
        <div style={{ flex: 1, display: recording ? "none" : "flex", alignItems: "center", background: "#f1f3f5", borderRadius: 999, padding: "4px 6px 4px 16px" }}>
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.nativeEvent.isComposing && handleSend()}
            disabled={confirmed || !active}
            placeholder={confirmed ? "该会话已确认提交" : active?.stage?.startsWith("review_") ? "打字或点麦克风说，Agent 会整理并跟你确认" : "点击气泡快速填入，或打字/语音输入"}
            style={{ flex: 1, border: "none", background: "none", outline: "none", fontSize: 14, minWidth: 0 }}
          />
        </div>
        <VoiceCapsuleInput
          disabled={confirmed || !active}
          onRecordingChange={(r) => {
            setRecording(r);
            recordingChanged?.(r);
          }}
          onTranscript={(text, mode) => {
            if (mode === "send") handleSend(draft.trim() ? `${draft.trimEnd()}${text}` : text, text);
            else {
              setRawPieces((prev) => [...prev, text]);
              setDraft((prev) => (prev.trim() ? `${prev.trimEnd()}${text}` : text));
            }
          }}
        />
        {!recording && (
        <button
          aria-label="实时语音会话"
          title="开始实时语音会话"
          disabled={confirmed || !active}
          onClick={() => setVoiceDialogOpen(true)}
          style={{
            border: "none", background: "#eef4fc", color: "#2a78d6", width: 40, height: 40,
            borderRadius: "50%", flexShrink: 0, cursor: confirmed || !active ? "default" : "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          <RealtimeVoiceIcon size={22} />
        </button>
        )}
        {voiceDialogOpen && (
          <RealtimeVoiceDialog
            turns={active?.turns ?? []}
            sending={sending}
            onSend={(text) => handleSend(text, text)}
            onClose={() => setVoiceDialogOpen(false)}
          />
        )}
        {!recording && (
        <button
          aria-label="发送"
          onClick={() => handleSend()}
          disabled={confirmed || sending || !draft.trim()}
          style={{
            border: "none",
            borderRadius: "50%",
            width: 40,
            height: 40,
            background: sending || confirmed || !draft.trim() ? "#a9c4e8" : "#2a78d6",
            color: "#fff",
            fontWeight: 700,
            flexShrink: 0,
          }}
        >
          ↑
        </button>
        )}
      </div>
    </div>
  );
}
