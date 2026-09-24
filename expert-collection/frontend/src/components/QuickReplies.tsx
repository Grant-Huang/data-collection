// Interactive quick-reply chips for the question currently being asked, rendered right under
// its bubble (not detached above the input box). Shared by desktop and mobile so both support
// multi-select the same way.
//
// PRD 18.4: a chip only ever fills the draft -- the expert still reviews/edits and presses
// send themselves. multi_select: chips toggle, "确认选择" puts the joined picks in the draft.
import { useEffect, useState } from "react";
import type { NextQuestion } from "../api/types";
import { isFallbackChip } from "../utils/chips";

interface Props {
  question: NextQuestion;
  onPick: (text: string) => void;
}

export function QuickReplies({ question, onPick }: Props) {
  const [selected, setSelected] = useState<string[]>([]);
  const chips = question.chips ?? [];
  const multi = question.chip_mode === "multi_select";

  // Selections are scoped to one question.
  useEffect(() => {
    setSelected([]);
  }, [question.target, question.question]);

  if (chips.length === 0) return null;

  function toggle(chip: string) {
    // "无" is exclusive with every other pick.
    setSelected((prev) => {
      if (prev.includes(chip)) return prev.filter((c) => c !== chip);
      if (chip === "无") return ["无"];
      return [...prev.filter((c) => c !== "无"), chip];
    });
  }

  return (
    <div className="chat-chips" role="group" aria-label="快捷回复">
      {chips.map((chip) => {
        const on = multi && selected.includes(chip);
        const cls = ["chip", isFallbackChip(chip) ? "fallback" : "", on ? "on" : ""].filter(Boolean).join(" ");
        return (
          <button
            key={chip}
            type="button"
            className={cls}
            aria-pressed={multi ? on : undefined}
            onClick={() => (multi ? toggle(chip) : onPick(chip))}
          >
            {chip}
          </button>
        );
      })}
      {multi && (
        <button
          type="button"
          className="chip-confirm"
          disabled={selected.length === 0}
          onClick={() => onPick(selected.join("、"))}
        >
          确认选择（{selected.length}）
        </button>
      )}
    </div>
  );
}
