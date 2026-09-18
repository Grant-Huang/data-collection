// Memory extraction (docs/app-design.md 7.3): reuses the dictation-cleanup mechanism's
// pattern (a lightweight qwen-turbo call via the server), just with a different prompt
// -- distills a completed user+assistant turn into 0+ standalone facts worth
// remembering, run async (off the critical path) after the reply is already showing.
// Replaces the old behavior of storing the user's raw ASR text every turn and never
// storing the assistant's reply at all -- see app.js's finalizeAssistantTurn(), the
// only caller.
//
// The raw transcript itself isn't lost by switching to this -- that's what
// ConversationHistory (history.js) already keeps a verbatim, unfiltered copy of;
// extraction produces a *different*, distilled thing (searchable memory fragments),
// it doesn't replace the traceable original. Everything extracted stays local-only
// (LocalMemory, memory.js) -- there is no external memory service to sync to.
const MemoryExtraction = (() => {
  /**
   * @param {string} userText
   * @param {string} assistantText
   */
  async function extractAndStore(userText, assistantText) {
    const knownJargon = LocalMemory.all()
      .filter((e) => e.isJargon)
      .slice(0, 20)
      .map((e) => e.text);

    let facts;
    try {
      const res = await fetch("/api/memory-extract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ userText, assistantText, knownJargon }),
      });
      if (!res.ok) throw new Error(`extract failed: ${res.status}`);
      const data = await res.json();
      facts = Array.isArray(data.facts) ? data.facts : [];
    } catch (e) {
      console.warn("memory extraction failed (this turn just won't be remembered):", e);
      return;
    }

    for (const fact of facts) {
      if (!fact || !fact.text) continue;
      LocalMemory.add(fact.text, { isJargon: !!fact.isJargon });
    }
  }

  return { extractAndStore };
})();
