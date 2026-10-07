// Display/draft helpers for quick-reply chips (PRD section 18). Pure functions so desktop
// and mobile behave identically.

// "No / not sure / skip" style answers -- rendered as visually secondary (dashed) chips so
// the structural answers read as the main options. Display-only; the backend never relies
// on this list.
const FALLBACK_PREFIXES = [
  "没有", "不确定", "先跳过", "规定和经验都有", "到这里整件事就结束了", "后面就处理完了", "不是，这是新的一步",
];

export function isFallbackChip(chip: string): boolean {
  return chip === "无" || FALLBACK_PREFIXES.some((p) => chip.startsWith(p));
}

// PRD 18.4 (revised, B8): a single-choice chip is a structural yes/no-style answer, so when the
// input box is empty one click sends it -- no second click on 「发送」. It still fills the draft
// instead when the expert has already typed something (their own words are never sent or
// dropped behind their back), and multi-select chips always build up a draft to send by hand.
// A pick sent by mistake is fixed the same way as any other answer: saying 「我说错了，……」
// (guide mode's correction path rolls the graph back to that turn).
export function chipSendsImmediately(chipMode: string | null | undefined, draft: string): boolean {
  return chipMode !== "multi_select" && !draft.trim();
}

// Otherwise chips go into the draft. If the draft is empty or is
// itself just an earlier chip pick, the new pick replaces it; if the expert already typed
// something of their own, the pick is appended instead of wiping what they wrote.
//
// An empty `pick` means a multi-select was toggled down to nothing: clear the draft if it only
// held earlier picks, otherwise leave the expert's own text alone.
export function mergeChipIntoDraft(draft: string, pick: string, chips: string[]): string {
  const current = draft.trim();
  if (!current) return pick;
  const draftIsOnlyChips = current.split("、").every((part) => chips.includes(part.trim()));
  if (draftIsOnlyChips) return pick;
  if (!pick) return current;
  if (current.includes(pick)) return current;
  return `${current}，${pick}`;
}

// Which of a past question's chips the expert's next message actually used -- lets the
// history show the frozen chip row with the pick highlighted.
export function pickedChips(chips: string[], answer: string | undefined): Set<string> {
  if (!answer) return new Set();
  const parts = answer.split("、").map((p) => p.trim());
  return new Set(chips.filter((c) => c === answer.trim() || parts.includes(c)));
}
