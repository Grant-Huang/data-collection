// PRD section 18: quick-reply chips only ever prefill the input box as an editable draft --
// they never auto-send, so the expert always has the chance to correct/qualify before
// committing, and open recall questions (chips === null) render as plain text with no chips.
import { useState } from "react";
import type { ConversationTurn, NextQuestion } from "../api/types";

interface Props {
  turns: ConversationTurn[];
  nextQuestion: NextQuestion | null;
  onSend: (text: string) => void;
  sending: boolean;
  confirmed: boolean;
}

export function ChatPanel({ turns, nextQuestion, onSend, sending, confirmed }: Props) {
  const [draft, setDraft] = useState("");

  function handleChip(chip: string) {
    setDraft(chip);
  }

  function handleSend() {
    const text = draft.trim();
    if (!text || sending) return;
    setDraft("");
    onSend(text);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ flex: 1, overflowY: "auto", padding: "16px", display: "flex", flexDirection: "column", gap: 12 }}>
        {turns.map((t) => (
          <div
            key={t.turn_id}
            style={{
              alignSelf: t.role === "expert" ? "flex-end" : "flex-start",
              maxWidth: "82%",
              background: t.role === "expert" ? "#2a78d6" : "#f1f3f5",
              color: t.role === "expert" ? "#fff" : "#1f2937",
              borderRadius: 12,
              padding: "8px 12px",
              fontSize: 13.5,
              lineHeight: 1.5,
              whiteSpace: "pre-wrap",
            }}
          >
            {t.text}
          </div>
        ))}
      </div>

      {nextQuestion?.chips && !confirmed && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, padding: "0 16px 8px" }}>
          {nextQuestion.chips.map((chip) => (
            <button
              key={chip}
              onClick={() => handleChip(chip)}
              style={{
                border: "1.3px solid #2a78d6",
                color: "#2a78d6",
                background: "#eef4fc",
                borderRadius: 999,
                padding: "6px 14px",
                fontSize: 12.5,
                cursor: "pointer",
              }}
            >
              {chip}
            </button>
          ))}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, padding: 16, borderTop: "1px solid #e5e7eb" }}>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          disabled={confirmed}
          placeholder={confirmed ? "该会话已确认提交，不能再修改" : "点击上方气泡快速填入，或直接输入你的回答"}
          rows={2}
          style={{
            flex: 1,
            resize: "none",
            border: "1px solid #d0d5dd",
            borderRadius: 8,
            padding: "8px 10px",
            fontSize: 13.5,
            fontFamily: "inherit",
          }}
        />
        <button
          onClick={handleSend}
          disabled={confirmed || sending || !draft.trim()}
          style={{
            border: "none",
            borderRadius: 8,
            padding: "0 18px",
            background: sending || confirmed ? "#a9c4e8" : "#2a78d6",
            color: "#fff",
            fontWeight: 600,
            cursor: sending || confirmed ? "default" : "pointer",
          }}
        >
          发送
        </button>
      </div>
    </div>
  );
}
