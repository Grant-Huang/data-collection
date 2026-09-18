// Full conversation history — every turn (user + assistant), from both the voice
// session and the text session, in one chronological, unfiltered record. This is a
// different grain of thing from LocalMemory (memory.js): that's a searchable,
// extracted-fragment store used to ground replies; this is the complete transcript
// itself, kept purely so it survives a reload (docs/app-design.md 8.4).
//
// Purely local (localStorage) — no external sync. Deliberately no search, no dedup.
// Does have a rolling-window trim (below) — see roadmap-todo.md's "原始对话记录加滚动窗口裁剪" item.
const ConversationHistory = (() => {
  const STORAGE_KEY = "voicechat.conversationHistory.v1";

  // "最近 N 条或最近 M 天，取较大者" (roadmap-todo.md): a turn survives a trim if it's
  // among the most recent MAX_ENTRIES, OR it's within the last MAX_AGE_DAYS -- the
  // union of both windows, not the intersection, so neither a quiet week (drops below
  // the count window) nor a single very active day (drops below the age window) gets
  // trimmed more aggressively than the other window alone would allow. Specific numbers
  // are a first-pass judgment call (the design discussion left them "TBD"), not a
  // measured/requested value -- easy to retune once there's a sense of real growth rate.
  const MAX_ENTRIES = 500;
  const MAX_AGE_DAYS = 30;
  const MAX_AGE_MS = MAX_AGE_DAYS * 24 * 60 * 60 * 1000;

  function load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (e) {
      return [];
    }
  }

  function persist(turns) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(turns));
    } catch (e) {
      // Storage full/unavailable — history just won't persist across reloads this session.
    }
  }

  let turns = load();

  function trim(list) {
    if (list.length <= MAX_ENTRIES) return list; // under the count window -- the age window can only keep more, nothing to do
    const cutoffTime = Date.now() - MAX_AGE_MS;
    const recentByCount = new Set(list.slice(-MAX_ENTRIES));
    return list.filter((t) => recentByCount.has(t) || t.timestamp >= cutoffTime);
  }

  return {
    /** @param {"user"|"assistant"} speaker */
    add(speaker, text) {
      const trimmed = (text || "").trim();
      if (!trimmed) return undefined;
      const turn = { speaker, text: trimmed, timestamp: Date.now() };
      turns.push(turn);
      turns = trim(turns);
      persist(turns);
      return turn;
    },

    all() {
      return [...turns];
    },

    clear() {
      turns = [];
      persist(turns);
    },
  };
})();
