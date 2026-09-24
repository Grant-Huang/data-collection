"""Machine-generated signals for the annotation panel (IMPLEMENTATION_PLAN.md section 15,
closing section 10's open item "标注面板本身还没读取这个信号").

Three sources, all rule-based and reproducible (no LLM):
1. graph_validator on the record's *current* graph (so a rework that breaks structure shows up),
   plus the same "no actor roles at all" check import precheck runs.
2. Within-version near-duplicate / micro-workflow-reuse matches, recomputed with
   import_pipeline.compare_within_batch -- the exact classification import used. Computed over
   the version's *original* records (these are signals about the imported data), cached per
   (version, thresholds) because a published version's records never change.
3. Cross-version matches stored at import time in version["precheck_issues"] (only versions
   imported after this change have them; earlier versions honestly show only 1 and 2 --
   recomputing against "everything published before this version" after the fact would
   compare against a different corpus than import actually did).
"""
from __future__ import annotations

from . import graph_validator, import_pipeline

_KIND_TEXT = {
    import_pipeline.DUPLICATE: ("error", "整体重复"),
    import_pipeline.MICROFLOW_REUSE_CANDIDATE: ("warning", "疑似微工作流复用"),
    import_pipeline.CONTENT_MATCH_STRUCTURE_DIFF: ("warning", "内容相近但结构不同"),
}

# Codes stored at import (routers/datasets.py import_confirm) for later display.
STORED_CODE_PREFIXES = ("version_",)

_within_cache: dict[tuple[str, float, float], dict[str, list[dict]]] = {}


def _within_version(version_id: str, records: list[dict], text_th: float, struct_th: float) -> dict[str, list[dict]]:
    key = (version_id, text_th, struct_th)
    if key in _within_cache:
        return _within_cache[key]
    names = {r.get("record_id"): (r.get("scenario") or {}).get("scenario_name") or r.get("record_id") for r in records}
    out: dict[str, list[dict]] = {}
    for m in import_pipeline.compare_within_batch(records, text_th, struct_th):
        level, label = _KIND_TEXT[m["kind"]]
        detail = f"文本相似度 {m['text_similarity']}，结构相似度 {m['structure_similarity']}"
        # A pair is reported once by compare_within_batch; show it on both records.
        for rid, other in ((m["record_id"], m["matched_record_id"]), (m["matched_record_id"], m["record_id"])):
            out.setdefault(rid, []).append({
                "level": level, "code": f"within_{m['kind']}",
                "message": f"与本版本记录「{names.get(other, other)}」{label}（{detail}）", "node_id": None,
            })
    _within_cache[key] = out
    return out


def graph_signals(graph: dict) -> list[dict]:
    out = [
        {"level": i["level"], "code": i["code"], "message": i["message"], "node_id": i.get("node_id")}
        for i in graph_validator.validate(graph)
    ]
    if graph.get("nodes") and not any(n.get("actor_roles") for n in graph["nodes"]):
        out.append({"level": "warning", "code": "missing_actor_roles", "message": "所有节点都没有角色信息", "node_id": None})
    return out


def version_signals(version: dict, records: list[dict], text_th: float, struct_th: float) -> dict[str, list[dict]]:
    """record_id -> signals that don't depend on the current graph (sources 2 and 3)."""
    out: dict[str, list[dict]] = {rid: list(sigs) for rid, sigs in _within_version(version["id"], records, text_th, struct_th).items()}
    for rid, issues in (version.get("precheck_issues") or {}).items():
        for i in issues:
            out.setdefault(rid, []).append({"level": "warning", "code": i["code"], "message": i["message"], "node_id": None})
    return out
