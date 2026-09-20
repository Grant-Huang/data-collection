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


def _find_near_duplicates(records: list[dict], text_threshold: float, structure_threshold: float) -> list[dict]:
    warnings: list[dict] = []
    text_cache = [(_record_text_shingles(r)) for r in records]
    struct_cache = [_record_structure_sets(r) for r in records]
    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            text_sim = _jaccard(text_cache[i], text_cache[j])
            node_sim = _jaccard(struct_cache[i][0], struct_cache[j][0])
            edge_sim = _jaccard(struct_cache[i][1], struct_cache[j][1])
            struct_sim = (node_sim + edge_sim) / 2
            rid_i, rid_j = records[i].get("record_id", f"#{i}"), records[j].get("record_id", f"#{j}")
            if text_sim >= text_threshold:
                warnings.append(_warn(
                    "near_duplicate_text",
                    f"记录 {rid_i} 与 {rid_j} 的文本相似度 {round(text_sim, 2)}，疑似近重复流程",
                ))
            if struct_sim >= structure_threshold:
                warnings.append(_warn(
                    "near_duplicate_structure",
                    f"记录 {rid_i} 与 {rid_j} 的结构相似度（节点/边类型集合近似值）{round(struct_sim, 2)}，疑似同模板改写",
                ))
    return warnings


def _find_cross_version_duplicates(
    records: list[dict], existing_records: list[dict], text_threshold: float, structure_threshold: float,
) -> list[dict]:
    """Strict gatekeeping against everything already published under the same source_type
    (IMPLEMENTATION_PLAN.md section 10) -- every import compares against the full existing
    corpus, not just whichever batch happened to be uploaded together in the same file.

    Deliberately different severities for text vs. structure, and both different from
    _find_near_duplicates' within-batch warnings:

    - Text similarity across versions is a precise, low-false-positive signal of genuine
      re-import (the same underlying content landing under a new record_id) -- this blocks
      import by default (error), through the same import_records_without_errors override
      every other precheck error already uses.
    - Structure-only similarity across versions is NOT blocked the same way. Verified against
      a real cross-version import: treating it as blocking made 0/40 new records importable,
      because the vast majority of hits were different scenarios (different industries,
      different text) that happen to share the same DAG skeleton -- exactly the kind of
      cross-scenario micro-workflow reuse the experimental design (§4.4) treats as an
      intentional, expected property of this data, not noise to reject. So a structure-only
      cross-version hit is reported as a warning (visible, not silently dropped) unless the
      same pair *also* clears the text threshold, in which case it's folded into the text
      error above rather than reported twice.

    `existing_records` entries are expected to carry a `_version_number` key (attached by the
    caller) purely for the message text; this function does not otherwise care where they
    came from, and does not touch the database itself.
    """
    if not existing_records:
        return []
    issues: list[dict] = []
    new_text = [_record_text_shingles(r) for r in records]
    new_struct = [_record_structure_sets(r) for r in records]
    exist_text = [_record_text_shingles(r) for r in existing_records]
    exist_struct = [_record_structure_sets(r) for r in existing_records]
    for i, new_r in enumerate(records):
        rid = new_r.get("record_id")
        for j, ex_r in enumerate(existing_records):
            text_sim = _jaccard(new_text[i], exist_text[j])
            node_sim = _jaccard(new_struct[i][0], exist_struct[j][0])
            edge_sim = _jaccard(new_struct[i][1], exist_struct[j][1])
            struct_sim = (node_sim + edge_sim) / 2
            ex_version = ex_r.get("_version_number", "?")
            ex_rid = ex_r.get("record_id")
            if text_sim >= text_threshold:
                issues.append(_err(
                    "cross_version_near_duplicate_text",
                    f"记录 {rid} 与已发布 v{ex_version} 版本中的 {ex_rid} 文本相似度 {round(text_sim, 2)}，"
                    f"疑似跨版本重复（严格把关：默认阻断导入，确认是合理的相似场景可勾选跳过错误继续导入）",
                    rid,
                ))
            elif struct_sim >= structure_threshold:
                # Structure-only overlap across versions is reported but not blocking --
                # see the docstring: verified against real data that treating this as an
                # error rejects legitimate cross-scenario template reuse wholesale.
                issues.append(_warn(
                    "cross_version_near_duplicate_structure",
                    f"记录 {rid} 与已发布 v{ex_version} 版本中的 {ex_rid} 结构相似度 {round(struct_sim, 2)}，"
                    f"结构相似但文本不同，未阻断导入，如需人工复核可在标注环节确认",
                    rid,
                ))
    return issues


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
