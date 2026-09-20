// PRD section 18: quick-reply chips only ever prefill the input box as an editable draft --
// they never auto-send, so the expert always has the chance to correct/qualify before
// committing, and open recall questions (chips === null) render as plain text with no chips.
//
// chip_mode "multi_select" (Case Context B-group, IMPLEMENTATION_PLAN.md section 9.1) is an
// extension of the same rule: chips toggle on/off, and a "确认选择" button joins the picks
// with "、" into the draft box -- still never auto-sends, the expert can still edit before
// hitting 发送.
import { useEffect, useState } from "react";
import type { ConversationTurn, NextQuestion } from "../api/types";
import { MessageList } from "./MessageList";

interface Props {
  turns: ConversationTurn[];
  nextQuestion: NextQuestion | null;
  onSend: (text: string) => void;
  sending: boolean;
  confirmed: boolean;
}

export function ChatPanel({ turns, nextQuestion, onSend, sending, confirmed }: Props) {
  const [draft, setDraft] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const isMultiSelect = nextQuestion?.chip_mode === "multi_select";

  // Selections are scoped to one question -- reset when the question changes so a leftover
  // selection from a previous B-group question can't leak into the next one.
  useEffect(() => {
    setSelected([]);
  }, [nextQuestion?.target, nextQuestion?.question]);

  function handleChip(chip: string) {
    setDraft(chip);
  }

  function toggleChip(chip: string) {
    setSelected((prev) => (prev.includes(chip) ? prev.filter((c) => c !== chip) : [...prev, chip]));
  }

  function handleConfirmSelection() {
    if (selected.length === 0) return;
    setDraft(selected.join("、"));
  }

  function handleSend() {
    const text = draft.trim();
    if (!text || sending) return;
    setDraft("");
    setSelected([]);
    onSend(text);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <MessageList turns={turns} />

      {nextQuestion?.chips && !confirmed && !isMultiSelect && (
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

      {nextQuestion?.chips && !confirmed && isMultiSelect && (
        <div style={{ padding: "0 16px 8px" }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
            {nextQuestion.chips.map((chip) => {
              const isOn = selected.includes(chip);
              return (
                <button
                  key={chip}
                  onClick={() => toggleChip(chip)}
                  style={{
                    border: "1.3px solid #2a78d6",
                    color: isOn ? "#fff" : "#2a78d6",
                    background: isOn ? "#2a78d6" : "#eef4fc",
                    borderRadius: 999,
                    padding: "6px 14px",
                    fontSize: 12.5,
                    cursor: "pointer",
                  }}
                >
                  {chip}
                </button>
              );
            })}
          </div>
          <button
            onClick={handleConfirmSelection}
            disabled={selected.length === 0}
            style={{
              border: "none",
              borderRadius: 8,
              padding: "6px 14px",
              fontSize: 12.5,
              fontWeight: 600,
              background: selected.length === 0 ? "#e5e7eb" : "#0ca30c",
              color: selected.length === 0 ? "#94a3b8" : "#fff",
              cursor: selected.length === 0 ? "default" : "pointer",
            }}
          >
            确认选择（{selected.length}）
          </button>
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
