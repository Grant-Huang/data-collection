// PRD 4.2/4.3: mobile session page = default home. Minimal top bar (hamburger + name + info),
// message list identical to desktop, capsule input row with mic (PRD 4.3.1).
import { useState } from "react";
import type { WorkflowRecord } from "../api/types";
import { MessageList } from "../components/MessageList";
import { VoiceInputCapsule } from "../voice/VoiceInputCapsule";

interface Props {
  active: WorkflowRecord | null;
  sending: boolean;
  onSend: (text: string) => void;
  onOpenDrawer: () => void;
  onToggleProgress: () => void;
  progressOpen: boolean;
  recordingChanged: (recording: boolean) => void;
}

export function MobileChatPage({ active, sending, onSend, onOpenDrawer, onToggleProgress, progressOpen, recordingChanged }: Props) {
  const [draft, setDraft] = useState("");
  const confirmed = active?.status === "expert_confirmed";
  const nextQuestion = active?.unresolved[0] ?? null;

  function handleChip(chip: string) {
    setDraft(chip);
  }

  function handleSend(text?: string) {
    const value = (text ?? draft).trim();
    if (!value || sending || confirmed) return;
    setDraft("");
    onSend(value);
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
        <MessageList turns={active.turns} />
      ) : (
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "#667085", fontSize: 13, padding: 24, textAlign: "center" }}>
          点击左上角「☰」新建一个流程开始讲述
        </div>
      )}

      {nextQuestion?.chips && !confirmed && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, padding: "0 14px 8px" }}>
          {nextQuestion.chips.map((chip) => (
            <button
              key={chip}
              onClick={() => handleChip(chip)}
              style={{
                border: "1.3px solid #2a78d6",
                color: "#2a78d6",
                background: "#eef4fc",
                borderRadius: 999,
                padding: "8px 14px",
                fontSize: 13,
                cursor: "pointer",
                minHeight: 44,
              }}
            >
              {chip}
            </button>
          ))}
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 14px", borderTop: "1px solid #e5e7eb" }}>
        <div style={{ flex: 1, display: "flex", alignItems: "center", background: "#f1f3f5", borderRadius: 999, padding: "4px 6px 4px 16px" }}>
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            disabled={confirmed || !active}
            placeholder={confirmed ? "该会话已确认提交" : "点击气泡快速填入，或打字/语音输入"}
            style={{ flex: 1, border: "none", background: "none", outline: "none", fontSize: 14, minWidth: 0 }}
          />
        </div>
        <VoiceInputCapsule
          disabled={confirmed || !active}
          sending={sending}
          turns={active?.turns ?? []}
          onRecordingChange={recordingChanged}
          onTranscript={(text, mode) => {
            if (mode === "send") handleSend(text);
            else setDraft(text);
          }}
        />
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
      </div>
    </div>
  );
}
