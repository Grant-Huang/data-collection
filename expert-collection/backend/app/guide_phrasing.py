"""Reply phrasing layer for the expert-collection guide (the "措辞器" half of the planner +
phraser split -- see guide_service.py's module docstring).

Division of labor, deliberately:
- guide_service.py's planner decides *what* to ask (deterministic, testable): it hands this
  module a template acknowledgement ("ack", a short restatement of what was just recorded)
  and a template question that are already correct and already anchored to the expert's
  own words (e.g. "「复测尺寸」之后，下一步是谁做什么？").
- This module only decides *how it sounds*. When the `guide_service` LLM slot is configured,
  the model rewrites the ack (and, for open recall questions only, the question) into more
  natural spoken Chinese. Every rewrite goes through `_validate` -- any rewrite that quotes
  something the expert never said, introduces a number the expert never said, uses graph
  jargon (PRD 3.2 "不问术语"), asks more than one question, or drops the anchor quote gets
  thrown away and the template is used instead. Any LLM failure also falls back to the
  template, same "never crash or hang the turn" rule as llm_client.py.

Why questions that come with chips are normally not rewritten: chips are the answer options
for that exact question (PRD section 18). A 7B model paraphrasing the question could shift
its meaning just enough that the chips stop being valid answers, and nothing here can verify
meaning -- so only the ack gets polished on those turns. The exception is a question whose
only chip is a generic "done" fallback (the planner marks it `rephrasable`), e.g. the main
path's "下一步是谁做什么？" + "后面就处理完了": that option stays valid for any wording.
"""
from __future__ import annotations

import json
import re

from . import llm_client
from . import settings as app_settings

# One-line "why am I asking this" hints, rendered under the question bubble (the `.why` line
# in design/conversation-chips-redesign.html). Deterministic by question target -- these are
# product copy, not model output, so they never need validating.
WHY_BY_TARGET: dict[str, str] = {
    "trigger_discovery": "先确定讲哪一件真实经历，后面的问题都围绕它展开。",
    "scenario_discovery": "了解起因和目标，后面整理步骤时才不会理解偏。",
    "case_context_discovery": "限制条件往往决定了当时为什么这么处理。",
    "main_path_discovery": "按时间顺序一步步讲，每一步都会变成图上的一个方框。",
    "end_condition_discovery": "知道做到哪一步算结束，流程图才完整。",
    "branch_discovery": "确认有没有“看情况处理”的地方，图上才不会漏掉例外情况。",
    "branch_condition": "把每种情况的判断条件说清楚，别人才能照着做。",
    "branch_rejoin": "确认例外情况处理完之后回到哪里，图才能接上。",
    "parallel_discovery": "同时进行的事情和先后做的事情，在图上的画法不一样。",
    "approval_discovery": "需要等人确认的地方，是流程里最容易卡住的环节。",
    "approval_who": "记下有权确认的人，交接关系才完整。",
    "retry_discovery": "返工情况是经验里最有价值的部分之一。",
    "retry_target": "确定返工回到哪一步，图上才能标清楚返工范围。",
    "experience_discovery": "规定之外的经验判断，是这份记录里最有价值的部分。",
    "correction_turn_pick": "回退后，图上那一步之后的内容会一起撤掉，重新讲。",
    "parallel_merge_discovery": "同时进行的事情和先后做的事情，在图上的画法不一样。",
    # Task layer (IMPLEMENTATION_PLAN.md section 18).
    "task_outline_discovery": "按负责方分好段，就能看出这件事由哪些人接力完成、在哪里交接。",
    "task_boundary_discovery": "确定每个任务从哪一步开始，两张图才能对得上。",
}

# PRD 3.2 rule 1 ("不问术语，只问业务"): the expert should never see graph vocabulary.
_BANNED_TERMS_RE = re.compile(r"分支|并行|汇合|节点|DAG|dag|拓扑|Loop|loop|有向图|边的|conditional|parallel")
_QUOTE_RE = re.compile(r"「([^」]+)」")
_DIGITS_RE = re.compile(r"\d+(?:\.\d+)?")

_MAX_ACK_LEN = 60
_MAX_QUESTION_LEN = 80

_SYSTEM_PROMPT = """你是制造业专家访谈助手，正在和一位一线专家聊天，帮他把一次真实经历整理成流程图。你现在只负责“说话的方式”，不负责决定问什么。

你会收到一个 JSON：
- last_expert_message：专家刚说的话
- recent_dialogue：最近几轮对话
- ack_draft：复述草稿（对专家刚才那句话的简短回应，可能为空）
- question_draft：问题草稿
- question_editable：是否允许改写问题

请输出一个 JSON object，只有两个字段：
- "ack"：把复述草稿改写得自然、口语化，像一位懂行的老同事在接话。一句话，不超过40个字，不要问号。只能复述专家原话里有的内容：不能添加专家没说过的人、数字、系统、原因或判断。可以为空字符串（比如专家只是点了个选项时，不用硬复述）。不要用“非常感谢”“好的好的”这类客套，也不要每次都用“明白”“好的”开头。
- "question"：question_editable 为 true 时，把问题草稿改写得更自然，但意思必须完全一致；只问一个问题；不超过50个字；草稿里「」括起来的内容必须原样保留。question_editable 为 false 时，原样返回问题草稿。

不要使用这些词：分支、并行、汇合、节点、DAG、拓扑。
只输出 JSON，不要有任何其他文字。"""


def _corpus(expert_texts: list[str], known_labels: list[str]) -> str:
    """Everything the expert has actually said (plus graph labels, which are themselves built
    only from the expert's own words) -- the only source a quote or number may come from."""
    return "\n".join([*expert_texts, *known_labels])


def _question_mark_count(text: str) -> int:
    return text.count("？") + text.count("?")


def _validate(ack: str, question: str, *, template_question: str, question_editable: bool,
              corpus: str) -> bool:
    """True only when the rewrite keeps every guarantee the template already had."""
    if len(ack) > _MAX_ACK_LEN or _question_mark_count(ack) > 0:
        return False
    if question_editable:
        if not question or len(question) > _MAX_QUESTION_LEN or _question_mark_count(question) > 1:
            return False
        # The anchor quote (e.g. 「复测尺寸」) is what makes the question specific -- the
        # rewrite must not drop it.
        for anchor in _QUOTE_RE.findall(template_question):
            if f"「{anchor}」" not in question:
                return False
    for part in (ack, question if question_editable else ""):
        if _BANNED_TERMS_RE.search(part):
            return False
        # Quotes and numbers must come from the expert, never from the model (PRD 3.2:
        # 不得编造角色、阈值).
        for quoted in _QUOTE_RE.findall(part):
            if quoted not in corpus:
                return False
        for num in _DIGITS_RE.findall(part):
            if num not in corpus:
                return False
    return True


def _llm_polish(slot_config: dict, *, ack: str, question: str, question_editable: bool,
                last_expert_message: str, recent_dialogue: list[dict]) -> tuple[str, str] | None:
    payload = {
        "last_expert_message": last_expert_message,
        "recent_dialogue": recent_dialogue,
        "ack_draft": ack,
        "question_draft": question,
        "question_editable": question_editable,
    }
    try:
        parsed = llm_client.chat_completion_json(slot_config, [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ])
    except llm_client.LLMError:
        return None
    new_ack, new_question = parsed.get("ack", ""), parsed.get("question", "")
    if not isinstance(new_ack, str) or not isinstance(new_question, str):
        return None
    return new_ack.strip(), new_question.strip()


def _recent_dialogue(history: list[dict], limit: int = 6) -> list[dict]:
    return [{"role": "专家" if t.get("role") == "expert" else "助手", "text": t.get("text", "")}
            for t in history[-limit:]]


def finalize(ack: str, next_question: dict | None, *, last_expert_message: str,
             history: list[dict] | None = None, known_labels: list[str] | None = None,
             closing_text: str | None = None) -> tuple[str, dict | None]:
    """Turns the planner's (template ack, template question) into the final reply.

    Returns (assistant_reply_text, next_question). `next_question` gets `ack`/`why` fields
    added (and its `question` possibly rephrased) so the frontend can render the three
    layers separately; `assistant_reply_text` is the plain concatenation, kept for every
    existing consumer that only reads the transcript text (exports, anonymization, ...).

    `closing_text` is for the final turn, which has no next question (review stage).
    """
    history = history or []
    known_labels = known_labels or []
    expert_texts = [t.get("text", "") for t in history if t.get("role") == "expert"] + [last_expert_message]
    corpus = _corpus(expert_texts, known_labels)

    question = next_question["question"] if next_question else (closing_text or "")
    question_editable = bool(next_question) and (not next_question.get("chips")
                                                 or bool(next_question.get("rephrasable")))

    slot_config = app_settings.resolve_slot_for_call(app_settings.get_effective_settings(), "guide_service")
    if (slot_config.get("enabled") and slot_config.get("endpoint") and slot_config.get("model_name")
            and last_expert_message):
        polished = _llm_polish(slot_config, ack=ack, question=question, question_editable=question_editable,
                               last_expert_message=last_expert_message,
                               recent_dialogue=_recent_dialogue(history))
        if polished is not None:
            new_ack, new_question = polished
            if _validate(new_ack, new_question, template_question=question,
                         question_editable=question_editable, corpus=corpus):
                ack = new_ack
                if question_editable:
                    question = new_question

    reply = f"{ack}{question}" if ack else question
    if next_question is None:
        return reply, None
    nq = {**{k: v for k, v in next_question.items() if k != "rephrasable"},
          "question": question, "ack": ack or None,
          "why": next_question.get("why") or WHY_BY_TARGET.get(next_question.get("target", ""))}
    return reply, nq
