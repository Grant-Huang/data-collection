#!/usr/bin/env python3
"""Offline comparison: the existing review-loop `intent` classification (embedded in a full
JSON generation, see app/review_agent.py `_call_review_model`) vs. an AnyJev-style typed
decision over the same six-way choice (edit/answer/satisfied/reject/adopt/other).

This script is deliberately read-only with respect to app/review_agent.py: it never edits
that module, and it drives the review loop only through its existing public entry point
(`review_agent.handle_turn`). The only "hook" is a monkeypatch of `llm_client.chat_completion_json`
for the duration of a run, installed via `unittest.mock.patch.object` and removed afterwards --
this lets us *observe* the exact messages sent to the model and the exact JSON it returned,
without changing what review_agent.py does or calling the model twice.

Two independent input modes, so this is useful with or without production data:

1. `--from-db` replays real historical annotate/arbitrate review sessions stored in
   `annotation_sessions` (see app/db.py `save_review_session`/`get_review_session`). Only the
   *final* state of each session is persisted (INSERT OR REPLACE by session id), so the
   pre-turn state at each historical step is not recoverable verbatim. Instead this replays
   the session's full `turns` transcript from scratch through `review_agent.new_state` +
   `review_agent.handle_turn`, in order -- i.e. it reconstructs a faithful conversation
   trajectory (same messages, same order) and lets the *current* model/code decide each step
   live, exactly as production would if this conversation happened today. This does not cover
   `mode="create"` sessions (stored inline on workflow records, not in `annotation_sessions`)
   or `mode="arbitrate"` sessions' exact original `candidates` snapshot (recomputed from
   current annotation history, which may have moved on) -- both are noted in the summary.

2. `--fixtures <path.jsonl>` takes a hand-curated set of cases, each one the exact positional
   arguments `review_agent._call_review_model` takes (state/graph/turns/text/offered), plus an
   optional "gold_intent" for accuracy scoring. This is the recommended path for building a
   stable, reviewable regression set (e.g. edge cases like "reject" vs "edit" worded
   ambiguously) that doesn't depend on what happens to be in the database today.

For each captured production call, this script optionally (`--engine both`) asks an AnyJev
`Decider` the *same* six-way choice question over the *same* prompt text, and reports:
  - agreement rate + confusion matrix between the chat-JSON intent and the AnyJev intent
  - per-class distribution of the chat-JSON intent (which classes are common vs. rare)
  - if `--labels` is given (a CSV of turn_id,gold_intent), accuracy of each approach and a
    coarse calibration check (AnyJev's top-class probability, bucketed, vs. observed accuracy)

Known unknown, flagged rather than guessed: AnyJev 0.1.0 (Pre-Alpha, see
https://pypi.org/project/anyjev/ and https://github.com/nokia-applied-research/AnyJev) does not
document the exact contract between `Question.choice(...)` and the `item` passed to
`Decider.decide(item, [question])` -- specifically how `item` is merged into the prompt the
backend actually sends to the model. `_anyjev_decide()` below makes the simplest reasonable
assumption (item = the same system+user text the chat path used) and isolates it behind one
function so it's a one-line fix if your installed version disagrees.

Usage:
    python scripts/eval_anyjev_intent.py --from-db --version-id v1 --limit 50
    python scripts/eval_anyjev_intent.py --fixtures fixtures/intent_cases.jsonl --engine both \
        --vllm-url http://localhost:8000 --model-path ./qwen3-4b-truncated --level L0
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

# Make `from app import ...` work the same way tests/conftest.py does (backend/ on sys.path),
# regardless of the caller's current working directory.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app import db, llm_client, review_agent  # noqa: E402

INTENT_LABELS = ["edit", "answer", "satisfied", "reject", "adopt", "other"]

# Literal prefix of review_agent._REVIEW_PROMPT -- used to tell a review-loop model call apart
# from the (also chat_completion_json-based) narrative-extraction call, since both go through
# the same llm_client function. If review_agent.py's prompt wording ever changes, this simply
# stops matching and the script reports zero captured calls instead of misattributing.
_REVIEW_PROMPT_MARK = "你是制造业流程审阅助手"


# --- capturing what review_agent actually sent to the model, without touching it -----------

@dataclass
class Probe:
    source: str          # "db:<session_id>" or "fixture:<line_no>"
    turn_id: str
    mode: str
    phase: str
    text: str
    messages: list[dict]
    chat_intent: str
    chat_latency_s: float
    gold_intent: str | None = None
    anyjev_intent: str | None = None
    anyjev_distribution: dict[str, float] | None = None
    anyjev_latency_s: float | None = None
    anyjev_error: str | None = None


class _Recorder:
    """Installed in place of llm_client.chat_completion_json for the duration of a replay.
    Passes every call straight through to the real implementation (so review_agent's behaviour
    is completely unchanged) and additionally records the review-loop ones."""

    def __init__(self):
        self.captured: list[dict[str, Any]] = []
        self._original = llm_client.chat_completion_json

    def __call__(self, cfg, messages, *, timeout=llm_client.DEFAULT_TIMEOUT_SECONDS):
        t0 = time.monotonic()
        result = self._original(cfg, messages, timeout=timeout)
        dt = time.monotonic() - t0
        system = messages[0]["content"] if messages and messages[0].get("role") == "system" else ""
        if system.startswith(_REVIEW_PROMPT_MARK):
            self.captured.append({"messages": messages, "result": result, "latency_s": dt})
        return result

    def drain(self) -> list[dict[str, Any]]:
        out, self.captured = self.captured, []
        return out


# --- mode 1: replay real sessions from annotation_sessions ----------------------------------

def _load_annotate_sessions(version_id: str | None, record_id: str | None, limit: int | None) -> list[dict]:
    """Read-only scan of annotation_sessions. Uses db.DB_PATH directly (same path app/db.py
    itself uses) instead of adding a new db.py function, so this stays a script-only concern."""
    conn = sqlite3.connect(db.DB_PATH)
    try:
        query = "SELECT data FROM annotation_sessions"
        params: list[Any] = []
        if version_id:
            query += " WHERE version_id = ?"
            params.append(version_id)
            if record_id:
                query += " AND record_id = ?"
                params.append(record_id)
        query += " ORDER BY updated_at DESC"
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()
    return [json.loads(r[0]) for r in rows]


def _replay_session(session: dict, recorder: _Recorder) -> tuple[list[Probe], list[str]]:
    """Re-drive review_agent.handle_turn over a stored session's transcript from scratch.
    Returns (probes captured from model calls made during this replay, warnings)."""
    warnings: list[str] = []
    mode = "arbitrate" if session.get("role_in_process") == "arbitration" else "annotate"
    if mode == "arbitrate":
        warnings.append(
            f"session {session['session_id']}: arbitrate mode replayed with candidates=[] "
            "(the original candidate snapshot at session-start time isn't stored) -- prompt "
            "context differs from what production actually saw for this session."
        )
    graph = copy.deepcopy(session["base_graph"])
    # Must go through opening(), not new_state() directly -- for annotate/arbitrate it also
    # sets phase="final_confirm" and seeds gaps, exactly as the router does when it stores
    # `session["review"] = opening.state` at session-start time. Skipping this made every
    # replayed turn take a different phase than production and silently captured nothing.
    state = review_agent.opening(review_agent.new_state(mode, base_graph=copy.deepcopy(graph), candidates=None), graph).state
    turns_so_far: list[dict] = []
    probes: list[Probe] = []
    stored_turns = session.get("turns", [])
    if stored_turns and stored_turns[0].get("role") == "assistant":
        turns_so_far.append(stored_turns[0])  # keep the real opening message as context
        stored_turns = stored_turns[1:]

    for turn in stored_turns:
        turns_so_far.append(turn)
        if turn.get("role") != "expert":
            continue  # assistant turns are replayed for context only, never re-decided
        recorder.drain()  # discard anything captured before this turn (should be none)
        try:
            result = review_agent.handle_turn(state, graph, turns_so_far, turn["text"], turn["turn_id"])
        except llm_client.LLMError as e:
            warnings.append(f"session {session['session_id']} turn {turn['turn_id']}: {e}")
            break  # state may be inconsistent past this point; stop replaying this session
        new_calls = recorder.drain()
        for call in new_calls:
            out = call["result"]
            intent = out.get("intent") if out.get("intent") in INTENT_LABELS else "other"
            probes.append(Probe(
                source=f"db:{session['session_id']}", turn_id=turn["turn_id"], mode=mode,
                phase=state.get("phase", "?"), text=turn["text"], messages=call["messages"],
                chat_intent=intent, chat_latency_s=call["latency_s"],
            ))
        if result.state is not None:
            state = result.state
        if result.graph is not None:
            graph = result.graph
        if result.finished:
            break
    return probes, warnings


# --- mode 2: hand-curated fixtures -----------------------------------------------------------

def _run_fixtures(path: Path, recorder: _Recorder) -> tuple[list[Probe], list[str]]:
    probes: list[Probe] = []
    warnings: list[str] = []
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            case = json.loads(line)
            recorder.drain()
            try:
                out = review_agent._call_review_model(
                    case["state"], case["graph"], case["turns"], case["text"], case.get("offered", []),
                )
            except llm_client.LLMError as e:
                warnings.append(f"fixture line {line_no}: {e}")
                continue
            calls = recorder.drain()
            if not calls:
                warnings.append(f"fixture line {line_no}: model was called but not captured "
                                 "(system prompt no longer matches _REVIEW_PROMPT_MARK?)")
                continue
            call = calls[-1]
            intent = out.get("intent") if out.get("intent") in INTENT_LABELS else "other"
            probes.append(Probe(
                source=f"fixture:{line_no}", turn_id=case.get("turn_id", f"line{line_no}"),
                mode=case["state"].get("mode", "?"), phase=case["state"].get("phase", "?"),
                text=case["text"], messages=call["messages"], chat_intent=intent,
                chat_latency_s=call["latency_s"], gold_intent=case.get("gold_intent"),
            ))
    return probes, warnings


# --- AnyJev side -------------------------------------------------------------------------

def _anyjev_decide(decider, question, probe: Probe) -> None:
    """Fills probe.anyjev_* in place. Isolated in one function because AnyJev 0.1.0's docs
    don't specify how `item` is supposed to relate to a Question's prompt (see module
    docstring) -- if your installed version wants something other than the raw prompt text,
    this is the only place to change."""
    item = "\n\n".join(m["content"] for m in probe.messages)
    t0 = time.monotonic()
    try:
        decision = decider.decide(item, [question])["intent"]
        probe.anyjev_latency_s = time.monotonic() - t0
        probe.anyjev_distribution = dict(decision.distribution)
        probe.anyjev_intent = max(probe.anyjev_distribution, key=probe.anyjev_distribution.get)
    except Exception as e:  # AnyJev/vLLM errors shouldn't take down the whole batch
        probe.anyjev_error = f"{type(e).__name__}: {e}"


def _build_anyjev(args) -> tuple[Any, Any]:
    try:
        from anyjev import Decider, Question
        from anyjev.backends.vllm import VLLMBackend
    except ImportError as e:
        raise SystemExit(
            "「--engine both」需要先 `pip install anyjev` 以及一个可达的 vLLM embed 服务 "
            "(vllm serve <truncated-model> --task embed ...)。见 "
            "https://pypi.org/project/anyjev/ 。"
        ) from e
    decider = Decider(VLLMBackend(args.vllm_url, args.model_path), level=args.level)
    question = Question.choice(
        "根据下面这段审阅对话的系统提示与上下文，模型接下来应该判定的 intent 是什么？",
        INTENT_LABELS, name="intent",
    )
    return decider, question


# --- reporting -------------------------------------------------------------------------

def _load_labels(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8") as f:
        return {row["turn_id"]: row["gold_intent"] for row in csv.DictReader(f)}


def _print_report(probes: list[Probe], warnings: list[str], have_anyjev: bool) -> None:
    print(f"\n共捕获 {len(probes)} 次审阅环节的模型判定（review_agent 未做任何改动，仅被动记录）。")
    if warnings:
        print(f"\n{len(warnings)} 条警告：")
        for w in warnings[:20]:
            print(f"  - {w}")
        if len(warnings) > 20:
            print(f"  ... 还有 {len(warnings) - 20} 条，见完整输出文件")

    print("\nchat-JSON intent 分布：")
    for label, count in Counter(p.chat_intent for p in probes).most_common():
        print(f"  {label:10s} {count}")

    scored = [p for p in probes if p.gold_intent]
    if scored:
        chat_acc = sum(p.chat_intent == p.gold_intent for p in scored) / len(scored)
        print(f"\n有人工标注 ground truth 的样本：{len(scored)} 条")
        print(f"  chat-JSON 准确率：{chat_acc:.1%}")

    if have_anyjev:
        ok = [p for p in probes if p.anyjev_intent is not None]
        errored = len(probes) - len(ok)
        print(f"\nAnyJev 成功判定 {len(ok)}/{len(probes)} 条（{errored} 条出错，见完整输出文件的 anyjev_error 字段）")
        if ok:
            agree = sum(p.chat_intent == p.anyjev_intent for p in ok)
            print(f"  与 chat-JSON 的一致率：{agree}/{len(ok)} = {agree / len(ok):.1%}")
            confusion: Counter[tuple[str, str]] = Counter((p.chat_intent, p.anyjev_intent) for p in ok)
            print("  混淆矩阵 (chat_intent -> anyjev_intent)：")
            for (a, b), count in confusion.most_common():
                marker = "" if a == b else "  <-- 不一致"
                print(f"    {a:10s} -> {b:10s} : {count}{marker}")
            scored_ok = [p for p in ok if p.gold_intent]
            if scored_ok:
                anyjev_acc = sum(p.anyjev_intent == p.gold_intent for p in scored_ok) / len(scored_ok)
                print(f"\n  AnyJev 准确率（有 ground truth 的 {len(scored_ok)} 条）：{anyjev_acc:.1%}")
                # coarse calibration: bucket by AnyJev's own top-class probability, compare to
                # observed accuracy in that bucket -- a well-calibrated 0.8 bucket should be
                # right about 80% of the time.
                buckets: dict[int, list[bool]] = defaultdict(list)
                for p in scored_ok:
                    top_prob = p.anyjev_distribution[p.anyjev_intent]
                    buckets[int(top_prob * 10)].append(p.anyjev_intent == p.gold_intent)
                print("  校准情况（AnyJev 报告的置信度分桶 vs 实际命中率）：")
                for bucket in sorted(buckets):
                    hits = buckets[bucket]
                    print(f"    置信度 {bucket/10:.1f}-{bucket/10 + 0.1:.1f}: "
                          f"{sum(hits)}/{len(hits)} = {sum(hits) / len(hits):.1%}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-db", action="store_true", help="replay real annotate/arbitrate sessions from the app DB")
    src.add_argument("--fixtures", type=Path, help="JSONL of hand-curated _call_review_model inputs")
    p.add_argument("--version-id", help="restrict --from-db to one dataset version")
    p.add_argument("--record-id", help="restrict --from-db to one record (requires --version-id)")
    p.add_argument("--limit", type=int, default=None, help="cap the number of sessions/fixture lines processed")
    p.add_argument("--engine", choices=["chat", "both"], default="chat",
                   help="'chat' only records the existing production intent (no AnyJev call, no extra deps); "
                        "'both' additionally asks AnyJev the same question")
    p.add_argument("--vllm-url", default="http://localhost:8000", help="AnyJev VLLMBackend embed server URL")
    p.add_argument("--model-path", help="path to the truncated model AnyJev's backend was started with")
    p.add_argument("--level", default="L0", choices=["L0", "L1", "L2"], help="AnyJev decision level")
    p.add_argument("--labels", type=Path, help="CSV with columns turn_id,gold_intent for accuracy scoring")
    p.add_argument("--out", type=Path, default=Path("anyjev_eval_results.jsonl"),
                   help="where to write one JSON line per probe for manual audit")
    args = p.parse_args()

    if args.engine == "both" and not args.model_path:
        p.error("--engine both 需要 --model-path（AnyJev 截断后模型的路径）")

    recorder = _Recorder()
    all_probes: list[Probe] = []
    all_warnings: list[str] = []

    with patch.object(llm_client, "chat_completion_json", recorder):
        if args.fixtures:
            probes, warnings = _run_fixtures(args.fixtures, recorder)
            all_probes += probes
            all_warnings += warnings
        else:
            sessions = _load_annotate_sessions(args.version_id, args.record_id, args.limit)
            if not sessions:
                p.error("--from-db 没有找到任何 annotation_sessions 记录（检查 --version-id/--record-id，"
                        "或先用 --fixtures 跑一份手工构造的测试集）")
            for session in sessions:
                probes, warnings = _replay_session(session, recorder)
                all_probes += probes
                all_warnings += warnings

    if args.labels:
        gold = _load_labels(args.labels)
        for probe in all_probes:
            probe.gold_intent = probe.gold_intent or gold.get(probe.turn_id)

    if args.engine == "both":
        decider, question = _build_anyjev(args)
        for probe in all_probes:
            _anyjev_decide(decider, question, probe)

    with args.out.open("w", encoding="utf-8") as f:
        for probe in all_probes:
            f.write(json.dumps(probe.__dict__, ensure_ascii=False) + "\n")
    print(f"逐条结果已写入 {args.out}")

    _print_report(all_probes, all_warnings, have_anyjev=(args.engine == "both"))


if __name__ == "__main__":
    main()
