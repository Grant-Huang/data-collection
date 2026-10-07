"""Editable read-back: the graph rendered as numbered, tagged lines the expert can edit directly,
and the line-by-line alignment that turns their edited copy back into a structured diff.

Why: reviewing is easier on the whole read-back than one question at a time, so the chat shows
it with a 「修改这段流程」 button that puts the text into the input box. The expert edits the
wording, deletes lines, adds lines, and sends it back. What changed is worked out here in code,
not guessed by the model:

- every line starts with the node's stable number `[seq]` (graph_ops.assign_missing_seqs: never
  renumbered, never reused) and, for non-plain steps, a type tag like 【判断】. Both are
  read-only -- they are how a line is matched to its node. If one was altered, duplicated or
  invented, the edit is refused and the expert told which line, instead of guessing;
- a numbered line whose text changed -> that node was revised; a numbered line that is gone ->
  that node is deleted; an unnumbered line -> a new step, positioned between the numbered lines
  around it.

The model then only has to interpret the *content* of the changed / added lines (rename,
different actor, new condition...), with the exact node ids attached. Deletions need no model
at all. A snapshot of the rendering is kept in the review state, and an edit is only accepted
against the graph it was rendered from -- a stale copy never edits a graph that changed since.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

TYPE_TAGS = {
    "start": "开始", "end": "结束", "decision": "判断", "approval": "审批", "handoff": "交接",
    "wait": "等待", "parallel_split": "同时进行", "parallel_join": "同时完成", "merge": "汇合",
}

_LINE_RE = re.compile(r"^\s*\[(\d+)\]\s*(?:【([^】]*)】)?\s*(.*?)\s*$")


def graph_signature(graph: dict) -> str:
    """Content signature of a graph (ignores layout-only fields), to tell whether the graph a
    read-back was rendered from is still the current one."""
    nodes = sorted(({k: v for k, v in n.items() if k not in ("manual_position",)} for n in graph.get("nodes", [])),
                   key=lambda n: n["node_id"])
    edges = sorted(graph.get("edges", []), key=lambda e: e["edge_id"])
    return hashlib.sha1(json.dumps([nodes, edges], ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def render(graph: dict, order: list[dict]) -> tuple[str, dict]:
    """(text, snapshot). `order` is the reading order (review_agent._topo_order). Branch targets
    and rework targets are referenced by number, so the structure is readable *and* survives
    the expert renaming the target step."""
    edges = graph.get("edges", [])
    num = {n["node_id"]: (n.get("seq") or i) for i, n in enumerate(order, 1)}

    def ref(node_id: str) -> str:
        return f"[{num[node_id]}]" if node_id in num else "（未知步骤）"

    lines, snapshot_lines = [], {}
    for n in order:
        nid, ntype = n["node_id"], n["node_type"]
        tag = TYPE_TAGS.get(ntype, "")
        prefix = f"[{num[nid]}]" + (f"【{tag}】" if tag else "")
        body = n["label"]
        if n.get("actor_roles"):
            body += f"（{'、'.join(n['actor_roles'])}）"
        outs = [e for e in edges if e["from"] == nid]
        if ntype == "decision" and outs:
            body += "：" + "；".join(f"{e.get('condition') or '（条件未说明）'} → {ref(e['to'])}" for e in outs)
        elif ntype == "parallel_split" and outs:
            body += "：" + "、".join(ref(e["to"]) for e in outs)
        elif len(outs) == 1 and ntype not in ("end",):
            nxt = outs[0]["to"]
            # Only spell out "then go to" when it isn't simply the next line -- keeps the common
            # straight-line case uncluttered while still showing every jump.
            pos = order.index(n)
            if pos + 1 >= len(order) or order[pos + 1]["node_id"] != nxt:
                cond = f"{outs[0]['condition']}，" if outs[0].get("condition") else ""
                body += f"；{cond}接着 → {ref(nxt)}"
        elif len(outs) > 1 and ntype not in ("decision", "parallel_split"):
            body += "；接着 → " + "、".join(
                (f"{e['condition']}：" if e.get("condition") else "") + ref(e["to"]) for e in outs)
        retry = n.get("retry_semantics") or {}
        if retry.get("enabled"):
            target = retry.get("rework_reference_node_id")
            body += (f"；{retry.get('condition') or '不合格'}时回到 {ref(target)} 重做" if target in num
                     else "；可能需要返工")
        if ntype != "start" and not any(e["to"] == nid for e in edges):
            body += "（前面没有接上任何步骤）"
        if ntype != "end" and not outs:
            body += "（之后没有接下去）"
        line = f"{prefix}{body}"
        lines.append(line)
        snapshot_lines[str(num[nid])] = {"node_id": nid, "tag": tag, "line": line, "body": body}
    snapshot = {"sig": graph_signature(graph), "lines": snapshot_lines, "order": [str(num[n["node_id"]]) for n in order]}
    return "\n".join(lines), snapshot


@dataclass
class EditDiff:
    changed: list[dict] = field(default_factory=list)   # {seq, node_id, before, after}
    deleted: list[dict] = field(default_factory=list)   # {seq, node_id, before}
    added: list[dict] = field(default_factory=list)     # {text, after_seq, before_seq}
    errors: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.changed or self.deleted or self.added)


def parse(text: str, snapshot: dict) -> EditDiff:
    """Align the expert's edited copy with the snapshot it came from, by number."""
    diff = EditDiff()
    lines = snapshot["lines"]
    seen: dict[str, int] = {}
    entries: list[tuple[str | None, str]] = []  # (seq or None for a new line, text)
    for lineno, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        m = _LINE_RE.match(raw)
        if not m:
            entries.append((None, raw.strip()))
            continue
        seq, tag, body = m.group(1), m.group(2) or "", m.group(3)
        if seq not in lines:
            diff.errors.append(f"第 {lineno} 行的编号 [{seq}] 在原来的流程里不存在")
            continue
        if seq in seen:
            diff.errors.append(f"编号 [{seq}] 出现了两次（第 {seen[seq]} 行和第 {lineno} 行）")
            continue
        seen[seq] = lineno
        if tag != lines[seq]["tag"]:
            was = f"【{lines[seq]['tag']}】" if lines[seq]["tag"] else "没有标签"
            now = f"【{tag}】" if tag else "没有标签"
            diff.errors.append(f"编号 [{seq}] 的标签被改了（原来是{was}，现在是{now}）")
            continue
        entries.append((seq, body))
    if diff.errors:
        return diff

    for seq in snapshot["order"]:
        if seq not in seen:
            diff.deleted.append({"seq": int(seq), "node_id": lines[seq]["node_id"], "before": lines[seq]["body"]})
    prev_seq: str | None = None
    for i, (seq, body) in enumerate(entries):
        if seq is None:
            nxt = next((s for s, _ in entries[i + 1:] if s is not None), None)
            diff.added.append({"text": body, "after_seq": int(prev_seq) if prev_seq else None,
                               "before_seq": int(nxt) if nxt else None})
            continue
        if _squash(body) != _squash(lines[seq]["body"]):
            diff.changed.append({"seq": int(seq), "node_id": lines[seq]["node_id"],
                                 "before": lines[seq]["body"], "after": body})
        prev_seq = seq
    return diff


def describe_for_model(diff: EditDiff) -> str:
    """The alignment result as the message the review model reads in place of the raw text."""
    out = ["对方没有用一句话描述，而是直接修改了流程复述文本。每行开头的 [编号] 就是流程图里节点的 seq，"
           "下面是系统按编号逐行比对出的改动（node_id 已经对好，直接用）："]
    for c in diff.changed:
        out.append(f"- 修改 [{c['seq']}]（node_id={c['node_id']}）：原来「{c['before']}」→ 现在「{c['after']}」")
    for a in diff.added:
        where = []
        if a["after_seq"] is not None:
            where.append(f"[{a['after_seq']}] 之后")
        if a["before_seq"] is not None:
            where.append(f"[{a['before_seq']}] 之前")
        out.append(f"- 新增一行（位于{'、'.join(where) or '最前面'}）：「{a['text']}」")
    for d in diff.deleted:
        out.append(f"- 删除 [{d['seq']}]（node_id={d['node_id']}）：原来「{d['before']}」——系统会删掉这一步并把前后接上，"
                   "你不要再对它出任何改图操作")
    out.append("请据此给出改图操作：修改行里改的可能是名称、执行人、条件或连到哪一步（→ [编号]），按改后的文字理解；"
               "新增行建成新步骤，接在它前后相邻的步骤之间。对方没有改的行不要动。")
    return "\n".join(out)


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)
