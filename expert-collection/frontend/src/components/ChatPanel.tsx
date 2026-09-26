// Desktop conversation column: message list (with the current question's quick-reply chips
// rendered under its bubble -- see MessageList/QuickReplies) plus the input box.
//
// PRD section 18: chips only ever prefill the input box as an editable draft -- they never
// auto-send, so the expert always has the chance to correct/qualify before committing, and
// open recall questions (chips === null) have no chips at all.
import { useEffect, useRef, useState } from "react";
import type { ConversationTurn, Graph, NextQuestion } from "../api/types";
import { mergeChipIntoDraft } from "../utils/chips";
import { MessageList } from "./MessageList";
import { VoiceDictationButton } from "./VoiceDictationButton";

interface Props {
  turns: ConversationTurn[];
  graph?: Graph | null;
  nextQuestion: NextQuestion | null;
  // rawTranscript: what speech recognition heard, when the message was dictated -- stored
  // next to the (possibly edited) text so recognition errors can be checked later.
  onSend: (text: string, rawTranscript?: string) => void;
  sending: boolean;
  confirmed: boolean;
  onHighlightNodes?: (nodeIds: string[] | null) => void;
  // Review-loop stage ("review_narrative" etc., section 17) -- only changes the input hint.
  stage?: string;
  // Text to append to the draft from outside (clicking a node on the graph quotes its name);
  // `nonce` makes repeated clicks on the same node count.
  insertText?: { text: string; nonce: number } | null;
  placeholder?: string;
}

export function ChatPanel({ turns, graph, nextQuestion, onSend, sending, confirmed, onHighlightNodes, stage, insertText, placeholder }: Props) {
  const [draft, setDraft] = useState("");
  // Raw recognizer output for everything dictated into the current draft.
  const [rawPieces, setRawPieces] = useState<string[]>([]);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  function handleChipPick(pick: string) {
    setDraft((prev) => mergeChipIntoDraft(prev, pick, nextQuestion?.chips ?? []));
    // Put the cursor in the box so the expert can edit the prefilled draft right away.
    requestAnimationFrame(() => {
      const el = inputRef.current;
      if (el) {
        el.focus();
        el.setSelectionRange(el.value.length, el.value.length);
      }
    });
  }

  useEffect(() => {
    if (!insertText?.text) return;
    setDraft((prev) => prev + insertText.text);
    requestAnimationFrame(() => inputRef.current?.focus());
  }, [insertText?.nonce]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleSend() {
    const text = draft.trim();
    if (!text || sending || confirmed) return;
    setDraft("");
    const raw = rawPieces.join("");
    setRawPieces([]);
    onSend(text, raw || undefined);
  }

  function handleDictated(text: string) {
    setRawPieces((prev) => [...prev, text]);
    setDraft((prev) => (prev.trim() ? `${prev.trimEnd()}${text}` : text));
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  const hasChips = !!nextQuestion?.chips?.length;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <MessageList
        turns={turns}
        graph={graph}
        activeQuestion={confirmed ? null : nextQuestion}
        onChipPick={handleChipPick}
        sending={sending}
        onHighlightNodes={onHighlightNodes}
      />

      <div style={{ position: "relative", display: "flex", gap: 8, padding: 16, borderTop: "1px solid var(--chat-line)", background: "#fff" }}>
        <VoiceDictationButton disabled={confirmed || sending} onText={handleDictated} />
        <textarea
          ref={inputRef}
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            if (!e.target.value.trim()) setRawPieces([]);
          }}
          onKeyDown={(e) => {
            // Don't send while an IME (Chinese input) composition is still open.
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              handleSend();
            }
          }}
          disabled={confirmed}
          placeholder={
            placeholder ?? (confirmed
              ? stage?.startsWith("review_")
                ? "已确认提交。要修改的话，点下方的「继续修改」"
                : "该会话已确认提交，不能再修改"
              : stage === "review_narrative"
                ? "把整件事从头到尾讲一遍，可以打字，也可以点 🎤 直接说。Enter 发送，Shift+Enter 换行"
                : stage?.startsWith("review_")
                  ? "回答上面的问题，或直接说哪里要改。Enter 发送，Shift+Enter 换行"
                  : hasChips
                    ? "点上面的选项快速填入（可修改），或直接输入你的回答"
                    : "按你记得的实际情况说就好，Enter 发送，Shift+Enter 换行")
          }
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
            background: sending || confirmed || !draft.trim() ? "#a9c4e8" : "var(--chat-accent)",
            color: "#fff",
            fontWeight: 600,
            cursor: sending || confirmed || !draft.trim() ? "default" : "pointer",
          }}
        >
          发送
        </button>
      </div>
    </div>
  );
}
