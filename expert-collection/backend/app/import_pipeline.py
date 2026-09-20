"""Public dataset import + precheck -- PRD 12.2, Phase 6 sub-scope (IMPLEMENTATION_PLAN.md
section 8). Upload format is exactly `schema/workflow_graph_schema_v2.json`'s
{dataset_meta, records[]} shape -- that's what PRD 12.2.1's "upload JSON" means concretely.

All ten precheck steps are rule/statistics-based, no LLM (PRD 15.3). Near-duplicate detection
uses exact word-level Jaccard similarity for text (not an approximate MinHash -- at the scale
a precheck report needs instant feedback for, exact is both simpler and more accurate) and a
node/edge-type-set Jaccard average as a cheap proxy for Graph Edit Distance (real GED is too
expensive to run pairwise in a live precheck; this is documented as an approximation, not
exact GED).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

from . import graph_validator, quality

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "docs" / "expert-workflow-collection" / "schema" / "workflow_graph_schema_v2.json"
)

_schema_cache: dict | None = None


def _load_schema() -> dict:
    global _schema_cache
    if _schema_cache is None:
        _schema_cache = json.loads(SCHEMA_PATH.read_text())
    return _schema_cache


VALID_MANUFACTURING_MODES = {
    "mass_repetitive", "high_automation", "high_mix_low_volume",
    "eto_mto", "large_project", "regulated_traceable", "other",
}
VALID_WORKFLOW_TYPES = {
    "exception_response", "standard_operation", "continuous_improvement", "change_introduction",
}


def _err(code: str, message: str, record_id: str | None = None) -> dict:
    return {"level": "error", "code": code, "message": message, "record_id": record_id}


def _warn(code: str, message: str, record_id: str | None = None) -> dict:
    return {"level": "warning", "code": code, "message": message, "record_id": record_id}


def _word_shingles(text: str) -> set[str]:
    # Character bigrams work better than word splitting for Chinese text, which has no
    # whitespace word boundaries.
    text = text.strip()
    return {text[i:i + 2] for i in range(len(text) - 1)} if len(text) >= 2 else {text} if text else set()


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _record_text_shingles(record: dict) -> set[str]:
    trigger = record.get("scenario", {}).get("trigger", "") or ""
    labels = " ".join(n.get("label", "") for n in record.get("graph", {}).get("nodes", []))
    return _word_shingles(trigger + labels)


def _record_structure_sets(record: dict) -> tuple[set[str], set[str]]:
    graph = record.get("graph", {})
    node_types = {n.get("node_type") for n in graph.get("nodes", [])}
    edge_types = {e.get("edge_type") for e in graph.get("edges", [])}
    return node_types, edge_types


# --- Duplicate / micro-workflow-reuse classification -----------------------------------
# Two-tier policy (per explicit product direction, not something the previous pure
# OR-threshold version got right on its own):
#
# 1. "整体重复" (whole-record duplicate): the SCENARIO is repeated *and* the WORKFLOW
#    (graph structure) is repeated -- text_sim AND struct_sim both clear their thresholds.
#    This is genuinely the same data landing twice and is treated as a blocking error.
# 2. "部分相似" (partial similarity / possible micro-workflow reuse): the scenario is
#    NOT the same (text_sim below threshold) but the structure is similar anyway --
#    struct_sim alone clears its threshold. This is the exact shape of legitimate
#    cross-scenario micro-workflow reuse (experimental design §4.4: the same operational
#    capability recurring across different end-to-end cases) and must not be treated as a
#    data-quality defect. Reported as a distinct, named signal (not blocking) so it can be
#    told apart from an actual duplicate rather than collapsed into one generic "near
#    duplicate" warning.
# A third, rarer combination -- text similar but structure different -- doesn't fit either
# story cleanly (same scenario described, different process) and is reported separately
# rather than silently merged into one of the two above.
#
# Both classifications remain a coarse, node/edge-*type-set* approximation (documented
# elsewhere in this module as a stand-in for real Graph Edit Distance), not exact subgraph
# matching -- "micro-workflow reuse candidate" here means "shares a DAG skeleton", not "we
# identified which specific reusable sub-workflow was reused." That finer-grained analysis
# belongs to the discovery pipeline (companion CWD experimental design), not import gating.

DUPLICATE = "duplicate"
MICROFLOW_REUSE_CANDIDATE = "microflow_reuse_candidate"
CONTENT_MATCH_STRUCTURE_DIFF = "content_match_structure_diff"


def _classify_pair(text_sim: float, struct_sim: float, text_threshold: float, structure_threshold: float) -> str | None:
    text_hit = text_sim >= text_threshold
    struct_hit = struct_sim >= structure_threshold
    if text_hit and struct_hit:
        return DUPLICATE
    if struct_hit:
        return MICROFLOW_REUSE_CANDIDATE
    if text_hit:
        return CONTENT_MATCH_STRUCTURE_DIFF
    return None


def _structure_similarity(a: tuple[set, set], b: tuple[set, set]) -> float:
    node_sim = _jaccard(a[0], b[0])
    edge_sim = _jaccard(a[1], b[1])
    return (node_sim + edge_sim) / 2


def _compare_within_batch(records: list[dict], text_threshold: float, structure_threshold: float) -> list[dict]:
    """Raw comparison results (no issue-level wrapping) for every pair within one upload
    batch. Reused by both precheck() (wraps these into _err/_warn issues) and could be
    reused directly by callers that just want the classification, same as
    compare_cross_version.
    """
    text_cache = [_record_text_shingles(r) for r in records]
    struct_cache = [_record_structure_sets(r) for r in records]
    matches: list[dict] = []
    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            text_sim = _jaccard(text_cache[i], text_cache[j])
            struct_sim = _structure_similarity(struct_cache[i], struct_cache[j])
            kind = _classify_pair(text_sim, struct_sim, text_threshold, structure_threshold)
            if kind is None:
                continue
            matches.append({
                "record_id": records[j].get("record_id", f"#{j}"),
                "matched_record_id": records[i].get("record_id", f"#{i}"),
                "matched_version_number": None,
                "text_similarity": round(text_sim, 3),
                "structure_similarity": round(struct_sim, 3),
                "kind": kind,
            })
    return matches


def compare_cross_version(
    records: list[dict], existing_records: list[dict], text_threshold: float, structure_threshold: float,
) -> list[dict]:
    """Public (no leading underscore -- used directly by routers/datasets.py's standalone
    /duplicate-check endpoint, not just internally by precheck) raw comparison of `records`
    against everything already published under the same source_type
    (IMPLEMENTATION_PLAN.md section 10: gatekeeping against the full existing corpus, not
    just the current upload batch). Returns one entry per (new record, existing record)
    pair that clears either threshold, classified via _classify_pair.

    `existing_records` entries are expected to carry a `_version_number` key (attached by
    the caller) purely so the output can say which published version the match is against;
    this function does not otherwise care where they came from and never touches the
    database itself.
    """
    if not existing_records:
        return []
    matches: list[dict] = []
    new_text = [_record_text_shingles(r) for r in records]
    new_struct = [_record_structure_sets(r) for r in records]
    exist_text = [_record_text_shingles(r) for r in existing_records]
    exist_struct = [_record_structure_sets(r) for r in existing_records]
    for i, new_r in enumerate(records):
        for j, ex_r in enumerate(existing_records):
            text_sim = _jaccard(new_text[i], exist_text[j])
            struct_sim = _structure_similarity(new_struct[i], exist_struct[j])
            kind = _classify_pair(text_sim, struct_sim, text_threshold, structure_threshold)
            if kind is None:
                continue
            matches.append({
                "record_id": new_r.get("record_id"),
                "matched_record_id": ex_r.get("record_id"),
                "matched_version_number": ex_r.get("_version_number"),
                "text_similarity": round(text_sim, 3),
                "structure_similarity": round(struct_sim, 3),
                "kind": kind,
            })
    return matches


_KIND_LABELS = {
    DUPLICATE: "整体重复",
    MICROFLOW_REUSE_CANDIDATE: "疑似微工作流复用",
    CONTENT_MATCH_STRUCTURE_DIFF: "内容相近但结构不同",
}


def _match_to_issue(m: dict, scope: str) -> dict:
    """scope: "batch" (within this upload) or "version" (against an already-published
    version) -- only affects the message text, not the classification.
    """
    label = _KIND_LABELS[m["kind"]]
    where = f"已发布 v{m['matched_version_number']} 版本中的 {m['matched_record_id']}" if scope == "version" else f"同批次记录 {m['matched_record_id']}"
    detail = f"文本相似度 {m['text_similarity']}，结构相似度 {m['structure_similarity']}"
    if m["kind"] == DUPLICATE:
        return _err(
            f"{scope}_duplicate",
            f"记录 {m['record_id']} 与{where}{label}（{detail}），判定为重复，默认阻断导入（确认属于合理的相似场景可勾选跳过错误继续导入）",
            m["record_id"],
        )
    return _warn(
        f"{scope}_{m['kind']}",
        f"记录 {m['record_id']} 与{where}{label}（{detail}），不阻断导入，如需人工复核可在 Prior 标注环节确认",
        m["record_id"],
    )


def _find_near_duplicates(records: list[dict], text_threshold: float, structure_threshold: float) -> list[dict]:
    return [_match_to_issue(m, "batch") for m in _compare_within_batch(records, text_threshold, structure_threshold)]


def _find_cross_version_duplicates(
    records: list[dict], existing_records: list[dict], text_threshold: float, structure_threshold: float,
) -> list[dict]:
    matches = compare_cross_version(records, existing_records, text_threshold, structure_threshold)
    return [_match_to_issue(m, "version") for m in matches]


def precheck(
    payload: dict, text_threshold: float, structure_threshold: float,
    existing_records: list[dict] | None = None,
) -> dict:
    """PRD 12.2.1's ten-step precheck, plus cross-version gatekeeping (IMPLEMENTATION_PLAN.md
    section 10). Returns a report; never writes to the database.

    existing_records: everything already published under this source_type across all prior,
    still-active dataset_versions -- the caller (routers/datasets.py) is responsible for
    fetching this from the database, so this module stays pure/DB-agnostic and testable with
    plain dicts. Pass None or [] to skip cross-version checks entirely (e.g. when the caller
    genuinely couldn't determine source_type yet).
    """
    issues: list[dict] = []

    # Step 1: JSON Schema validation
    try:
        jsonschema.validate(payload, _load_schema())
    except jsonschema.ValidationError as e:
        issues.append(_err("schema_invalid", f"JSON Schema 校验失败：{e.message}（路径：{'/'.join(str(p) for p in e.path)}）"))
        return _report(payload, issues, [], text_threshold, structure_threshold)

    dataset_meta = payload["dataset_meta"]
    records = payload["records"]
    meta_source_type = dataset_meta["source_type"]
    existing_ids = {r.get("record_id") for r in (existing_records or [])}

    seen_ids: set[str] = set()
    for r in records:
        rid = r.get("record_id")

        # Step 2: source_type consistency
        prov_source = r.get("provenance", {}).get("source_type")
        if prov_source and prov_source != meta_source_type:
            issues.append(_err("source_type_mismatch", f"记录 {rid} 的 provenance.source_type（{prov_source}）与数据集 source_type（{meta_source_type}）不一致", rid))

        # Step 3: required field completeness (beyond schema's own required list)
        if not r.get("scenario", {}).get("trigger"):
            issues.append(_warn("missing_trigger", f"记录 {rid} 缺少触发场景描述（scenario.trigger）", rid))

        # Step 4: manufacturing_mode / workflow_type enum check
        mode = r.get("manufacturing_context", {}).get("manufacturing_mode")
        if mode and mode not in VALID_MANUFACTURING_MODES:
            issues.append(_err("invalid_manufacturing_mode", f"记录 {rid} 的 manufacturing_mode 非法值：{mode}", rid))
        wtype = r.get("scenario", {}).get("workflow_type")
        if wtype and wtype not in VALID_WORKFLOW_TYPES:
            issues.append(_err("invalid_workflow_type", f"记录 {rid} 的 workflow_type 非法值：{wtype}", rid))

        # Step 5: Graph Validator (same rules as expert collection, PRD 3.3/3.4)
        for v_issue in graph_validator.validate(r.get("graph", {})):
            issues.append({**v_issue, "record_id": rid})

        # Step 6: record_id uniqueness -- within this upload batch, and against every
        # record_id already published under this source_type (cross-version gatekeeping).
        if rid in seen_ids:
            issues.append(_err("duplicate_record_id", f"record_id 重复：{rid}", rid))
        elif rid in existing_ids:
            issues.append(_err(
                "record_id_already_exists",
                f"record_id {rid} 已存在于历史已发布版本中，需要改用新的 record_id 才能导入",
                rid,
            ))
        seen_ids.add(rid)

        # Step 8: entity/role completeness
        has_roles = any(n.get("actor_roles") for n in r.get("graph", {}).get("nodes", []))
        if not has_roles:
            issues.append(_warn("missing_actor_roles", f"记录 {rid} 所有节点都没有角色信息", rid))

    # Step 7: near-duplicate detection -- within this batch (warning) and against the
    # existing published corpus of this source_type (error, see _find_cross_version_duplicates).
    issues.extend(_find_near_duplicates(records, text_threshold, structure_threshold))
    issues.extend(_find_cross_version_duplicates(records, existing_records or [], text_threshold, structure_threshold))

    return _report(payload, issues, records, text_threshold, structure_threshold)


def _report(payload: dict, issues: list[dict], records: list[dict], text_threshold: float, structure_threshold: float) -> dict:
    error_count = sum(1 for i in issues if i["level"] == "error")
    warning_count = sum(1 for i in issues if i["level"] == "warning")
    # A record with any error against it is not importable; records with only warnings are.
    error_record_ids = {i["record_id"] for i in issues if i["level"] == "error" and i.get("record_id")}
    importable = [r for r in records if r.get("record_id") not in error_record_ids]

    graphs = [r["graph"] for r in importable]
    preview = quality.compute_readiness(graphs) if graphs else None

    # Step 9: Gold annotation availability -- honest, this system has no annotation pipeline yet.
    gold_note = "本系统尚未实现标注体系（见 Phase 3 annotation_readiness 维度），Gold 标注可用性统一记为不可用。"

    # Step 10: usage recommendation
    if error_count > 0:
        recommendation = "需人工复核"
    elif preview and preview["overall"] is not None and preview["overall"] >= 70:
        recommendation = "可用于主实验"
    elif preview and preview["overall"] is not None and preview["overall"] >= 50:
        recommendation = "适合辅助实验"
    elif preview and preview["overall"] is None:
        recommendation = "需人工复核"
    else:
        recommendation = "不建议使用"

    return {
        "total_records": len(records),
        "importable_records": len(importable),
        "error_count": error_count,
        "warning_count": warning_count,
        "issues": issues,
        "preview_readiness": preview,
        "gold_annotation_note": gold_note,
        "recommendation": recommendation,
        "text_threshold": text_threshold,
        "structure_threshold": structure_threshold,
        "importable_record_ids": [r.get("record_id") for r in importable],
    }
