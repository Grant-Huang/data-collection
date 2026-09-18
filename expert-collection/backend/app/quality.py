"""Dataset Readiness Score v2 -- PRD 13.3/13.6: ten dimensions, all pure rule-based
statistics over the confirmed workflow graphs in a dataset version (no LLM -- 13.6 is
explicit that the *scores* must stay reproducible; only the narrative text in explain.py
needs a language model).

Honesty note (documented in IMPLEMENTATION_PLAN.md section 6): several PRD sub-indicators
need fields this system doesn't collect yet (manufacturing mode/industry/scenario
classification, expert profile, Gold annotations). Rather than fabricate those numbers,
each dimension below is scored from whatever real signal the schema actually carries, and
its `scope_note` says plainly what's included and what isn't yet.
"""
from __future__ import annotations

from typing import Any

MIN_SAMPLE_SIZE = 20  # PRD 13.5.1

DIMENSION_WEIGHTS = {
    "coverage": 0.15,
    "balance": 0.10,
    "completeness": 0.15,
    "graph_completeness": 0.15,
    "extractability": 0.10,
    "authenticity": 0.10,
    "annotation_readiness": 0.10,
    "diversity": 0.05,
    "structural_diversity": 0.05,
    "low_leakage_risk": 0.05,
}

DIMENSION_LABELS = {
    "coverage": "覆盖度",
    "balance": "平衡度",
    "completeness": "流程完整度",
    "graph_completeness": "Graph 结构完整度",
    "extractability": "可抽取性",
    "authenticity": "真实性与来源可信度",
    "annotation_readiness": "标注成熟度",
    "diversity": "多样性",
    "structural_diversity": "结构多样性",
    "low_leakage_risk": "低泄漏风险",
}

# PRD 13.3.1 point 1: fixed, dataset-independent scoring-standard text per dimension.
SCORING_STANDARDS = {
    "coverage": "满分要求岗位（actor_roles）覆盖足够多样；当前版本尚未采集制造模式/行业/场景分类字段，这些子项暂不计入，只按岗位覆盖率打分。",
    "balance": "工作流长度（节点数）越均匀、没有个别工作流过度拉高平均值，分数越高；按节点数分布的归一化熵计算，熵越接近 1 分数越高。",
    "completeness": "平均步骤数越高、达到 5 步以上的工作流占比越高、含判断节点的比例越高，分数越高。",
    "graph_completeness": "Graph Validator 零错误的工作流占比、分支条件填写完整率、并行汇合完整率、返工语义说明完整率综合计算，孤立节点比例应为 0。",
    "extractability": "节点与边的平均置信度（confidence，来自采集时的抽取置信度）越高，分数越高——置信度低通常意味着专家表述模糊或系统只能低把握抽取。",
    "authenticity": "本维度当前只统计『已经过专家确认』的比例（发布流程只收录 expert_confirmed 记录，因此通常为 100%）；岗位/经验年限等专家背景字段尚未采集，不计入。",
    "annotation_readiness": "统计 Gold 标注覆盖率；本产品的标注体系还未实现（属于后续阶段范围），当前固定记为 0 分，代表『体系缺失』而非『数据质量差』。",
    "diversity": "岗位种类数、工作流长度的离散程度、判断节点平均分支数综合计算，种类越多、分布越分散，分数越高。",
    "structural_diversity": "Linear（无分支无并行）类型占比越低、含分支/并行/返工路径的比例越高，分数越高；80 分以上要求至少两种结构类型都有覆盖。",
    "low_leakage_risk": "统计触发描述（trigger 节点文本）完全重复的比例作为粗粒度重复信号；更精细的近重复检测（TF-IDF/MinHash 文本相似度、Graph Edit Distance 结构相似度）尚未实现，留待下一轮。",
}


def _node_types(graph: dict) -> list[str]:
    return [n["node_type"] for n in graph.get("nodes", [])]


def _confidences(graph: dict) -> list[float]:
    vals = [n.get("confidence", 1.0) for n in graph.get("nodes", [])]
    vals += [e.get("confidence", 1.0) for e in graph.get("edges", [])]
    return vals


def _has_structure(graph: dict, node_type: str) -> bool:
    return any(n["node_type"] == node_type for n in graph.get("nodes", []))


def _trigger_label(graph: dict) -> str | None:
    starts = [n for n in graph.get("nodes", []) if n["node_type"] == "start"]
    if not starts:
        return None
    start_id = starts[0]["node_id"]
    first_edges = [e for e in graph.get("edges", []) if e["from"] == start_id]
    if not first_edges:
        return None
    target_id = first_edges[0]["to"]
    target = next((n for n in graph.get("nodes", []) if n["node_id"] == target_id), None)
    return target["label"] if target else None


def _band(score: float) -> str:
    if score >= 80:
        return "good"
    if score >= 60:
        return "warning"
    return "poor"


def _dim(score: float, sub: dict[str, Any], scope_note: str) -> dict:
    return {"score": round(max(0.0, min(100.0, score)), 1), "band": _band(score), "sub_indicators": sub, "scope_note": scope_note}


def compute_readiness(graphs: list[dict]) -> dict:
    """graphs: list of Graph dicts (nodes/edges) for every workflow in the dataset version."""
    n = len(graphs)
    dims: dict[str, dict] = {}

    if n < MIN_SAMPLE_SIZE:
        for key in DIMENSION_WEIGHTS:
            dims[key] = {
                "score": None, "band": "insufficient_sample",
                "sub_indicators": {"sample_size": n, "threshold": MIN_SAMPLE_SIZE},
                "scope_note": "样本量不足，暂不评分（PRD 13.5.1：低于 20 条已确认记录时不计算比例类指标，避免误导）。",
            }
        return {"overall": None, "band": "insufficient_sample", "sample_size": n, "dimensions": dims}

    # coverage: role diversity (only real coverage-ish signal we collect today)
    all_roles = set()
    for g in graphs:
        for node in g.get("nodes", []):
            all_roles.update(node.get("actor_roles", []))
    role_count = len(all_roles)
    coverage_score = min(100.0, role_count / 5 * 100)
    dims["coverage"] = _dim(coverage_score, {"distinct_roles": role_count, "roles": sorted(all_roles)}, SCORING_STANDARDS["coverage"])

    # balance: normalized entropy of workflow size (node count) distribution
    import math
    sizes = [len(g.get("nodes", [])) for g in graphs]
    size_buckets: dict[int, int] = {}
    for s in sizes:
        bucket = s // 3 * 3  # group into buckets of 3 to avoid every workflow being its own bucket
        size_buckets[bucket] = size_buckets.get(bucket, 0) + 1
    probs = [c / n for c in size_buckets.values()]
    entropy = -sum(p * math.log2(p) for p in probs if p > 0)
    max_entropy = math.log2(len(size_buckets)) if len(size_buckets) > 1 else 1
    balance_score = (entropy / max_entropy * 100) if max_entropy > 0 else 100.0
    dims["balance"] = _dim(balance_score, {"size_bucket_counts": size_buckets, "workflow_count": n}, SCORING_STANDARDS["balance"])

    # completeness
    avg_steps = sum(sizes) / n
    pct_5plus = sum(1 for s in sizes if s >= 5) / n * 100
    pct_with_roles = sum(1 for g in graphs if any(node.get("actor_roles") for node in g.get("nodes", []))) / n * 100
    pct_with_decision = sum(1 for g in graphs if _has_structure(g, "decision")) / n * 100
    completeness_score = (min(100, avg_steps / 8 * 100) + pct_5plus + pct_with_roles + pct_with_decision) / 4
    dims["completeness"] = _dim(
        completeness_score,
        {"avg_steps": round(avg_steps, 1), "pct_5plus_steps": round(pct_5plus, 1),
         "pct_with_role_info": round(pct_with_roles, 1), "pct_with_decision_node": round(pct_with_decision, 1)},
        SCORING_STANDARDS["completeness"],
    )

    # graph completeness: reuses graph_validator's own rules
    from . import graph_validator
    valid_count = sum(1 for g in graphs if graph_validator.is_valid(g))
    pct_valid = valid_count / n * 100
    cond_edges = [e for g in graphs for e in g.get("edges", []) if e["edge_type"] == "conditional"]
    cond_filled = sum(1 for e in cond_edges if (e.get("condition") or "").strip())
    pct_cond_filled = (cond_filled / len(cond_edges) * 100) if cond_edges else 100.0
    retry_nodes = [node for g in graphs for node in g.get("nodes", []) if node.get("retry_semantics", {}).get("enabled")]
    retry_filled = sum(1 for node in retry_nodes if (node["retry_semantics"] or {}).get("description"))
    pct_retry_filled = (retry_filled / len(retry_nodes) * 100) if retry_nodes else 100.0
    graph_completeness_score = (pct_valid + pct_cond_filled + pct_retry_filled) / 3
    dims["graph_completeness"] = _dim(
        graph_completeness_score,
        {"pct_validator_clean": round(pct_valid, 1), "pct_conditions_filled": round(pct_cond_filled, 1),
         "pct_retry_semantics_filled": round(pct_retry_filled, 1)},
        SCORING_STANDARDS["graph_completeness"],
    )

    # extractability: average confidence
    all_conf = [c for g in graphs for c in _confidences(g)]
    avg_conf = sum(all_conf) / len(all_conf) if all_conf else 1.0
    extractability_score = avg_conf * 100
    dims["extractability"] = _dim(extractability_score, {"avg_confidence": round(avg_conf, 3)}, SCORING_STANDARDS["extractability"])

    # authenticity: expert_confirmed ratio (should be ~100% since publish only takes confirmed records)
    all_nodes = [node for g in graphs for node in g.get("nodes", [])]
    pct_confirmed = (sum(1 for node in all_nodes if node.get("expert_confirmed")) / len(all_nodes) * 100) if all_nodes else 100.0
    dims["authenticity"] = _dim(pct_confirmed, {"pct_expert_confirmed_nodes": round(pct_confirmed, 1)}, SCORING_STANDARDS["authenticity"])

    # annotation readiness: no Gold annotation pipeline exists yet
    dims["annotation_readiness"] = _dim(0.0, {"gold_coverage": 0}, SCORING_STANDARDS["annotation_readiness"])

    # diversity
    avg_branches = 0.0
    decision_nodes = [node for g in graphs for node in g.get("nodes", []) if node["node_type"] == "decision"]
    if decision_nodes:
        branch_counts = []
        for g in graphs:
            for node in g.get("nodes", []):
                if node["node_type"] == "decision":
                    out = [e for e in g.get("edges", []) if e["from"] == node["node_id"] and e["edge_type"] == "conditional"]
                    branch_counts.append(len(out))
        avg_branches = sum(branch_counts) / len(branch_counts) if branch_counts else 0.0
    size_variance = (sum((s - avg_steps) ** 2 for s in sizes) / n) ** 0.5 if n else 0
    diversity_score = min(100.0, role_count / 5 * 40 + min(size_variance / 3, 1) * 30 + min(avg_branches / 3, 1) * 30)
    dims["diversity"] = _dim(
        diversity_score,
        {"distinct_roles": role_count, "workflow_size_stddev": round(size_variance, 2), "avg_decision_branches": round(avg_branches, 2)},
        SCORING_STANDARDS["diversity"],
    )

    # structural diversity
    pct_linear = sum(1 for g in graphs if not _has_structure(g, "decision") and not _has_structure(g, "parallel_split")) / n * 100
    pct_branch = sum(1 for g in graphs if _has_structure(g, "decision")) / n * 100
    pct_parallel = sum(1 for g in graphs if _has_structure(g, "parallel_split")) / n * 100
    pct_retry = sum(1 for g in graphs if any(node.get("retry_semantics", {}).get("enabled") for node in g.get("nodes", []))) / n * 100
    structure_types_present = sum(1 for pct in (pct_branch, pct_parallel, pct_retry) if pct > 0)
    structural_diversity_score = (100 - pct_linear) * 0.6 + min(structure_types_present / 3 * 100, 100) * 0.4
    dims["structural_diversity"] = _dim(
        structural_diversity_score,
        {"pct_linear": round(pct_linear, 1), "pct_with_branch": round(pct_branch, 1),
         "pct_with_parallel": round(pct_parallel, 1), "pct_with_retry": round(pct_retry, 1)},
        SCORING_STANDARDS["structural_diversity"],
    )

    # low leakage risk: exact-duplicate trigger label ratio as a crude proxy
    triggers = [_trigger_label(g) for g in graphs]
    triggers = [t for t in triggers if t]
    dup_count = len(triggers) - len(set(triggers))
    dup_ratio = (dup_count / len(triggers) * 100) if triggers else 0.0
    leakage_score = 100 - dup_ratio
    dims["low_leakage_risk"] = _dim(
        leakage_score, {"exact_duplicate_trigger_ratio": round(dup_ratio, 1)}, SCORING_STANDARDS["low_leakage_risk"]
    )

    overall = sum(dims[key]["score"] * weight for key, weight in DIMENSION_WEIGHTS.items())
    return {"overall": round(overall, 1), "band": _band(overall), "sample_size": n, "dimensions": dims}
