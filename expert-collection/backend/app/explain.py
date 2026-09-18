"""Mock Explanation Generator -- stands in for the real LLM narrative step from PRD 13.3.1/
13.6 (same pattern as guide_service.py's Mock Guide Service): turns the rule-computed
statistics from quality.py into a plain-language "why this score" paragraph, citing 1-2
concrete sample workflows the way a real model would be asked to. Call signature
(dimension_key, dim_result, sample_workflows) -> str is what a real model call would take
too (statistics + candidate examples in, one paragraph out), so swapping in a real L/C-tier
model later only touches this module.

Honesty: every number quoted in the generated text is read directly out of `dim_result` --
nothing here is invented, only the sentence templates are fixed in advance (that's the
"reads more naturally" part the PRD says an LLM would add over a bare template).
"""
from __future__ import annotations

from typing import Any

from .quality import DIMENSION_LABELS


def _sample_names(workflows: list[dict], limit: int = 2) -> list[str]:
    return [w.get("name", w.get("id", "?")) for w in workflows[:limit]]


def explain_dimension(key: str, dim: dict[str, Any], workflows: list[dict]) -> str:
    label = DIMENSION_LABELS.get(key, key)
    if dim["score"] is None:
        return f"{label}：当前已确认记录数 {dim['sub_indicators']['sample_size']} 条，低于 {dim['sub_indicators']['threshold']} 条的最低统计门槛，暂不生成分数依据。"

    sub = dim["sub_indicators"]
    score = dim["score"]
    examples = _sample_names(workflows)
    example_text = "、".join(f"《{e}》" for e in examples) if examples else "（暂无可举例样本）"

    if key == "coverage":
        return (
            f"当前 {score} 分，基于数据集里出现过的 {sub['distinct_roles']} 种不同岗位角色"
            f"（{'、'.join(sub['roles']) if sub['roles'] else '暂无'}）计算。"
            f"制造模式/行业/场景分类字段本产品尚未采集，这部分暂不计入覆盖度。"
        )
    if key == "balance":
        buckets = sub["size_bucket_counts"]
        biggest = max(buckets, key=lambda k: buckets[k]) if buckets else None
        return (
            f"当前 {score} 分，{sub['workflow_count']} 条工作流按步骤数分桶后共 {len(buckets)} 个规模区间，"
            + (f"其中步骤数在 {biggest}~{biggest+2} 区间的工作流最多，占比偏高会拉低本项分数。" if biggest is not None else "")
        )
    if key == "completeness":
        return (
            f"当前 {score} 分，平均每条工作流 {sub['avg_steps']} 个步骤，"
            f"{sub['pct_5plus_steps']}% 的工作流达到 5 步及以上，{sub['pct_with_role_info']}% 含明确角色信息，"
            f"{sub['pct_with_decision_node']}% 含判断节点，例如 {example_text}。"
        )
    if key == "graph_completeness":
        return (
            f"当前 {score} 分：{sub['pct_validator_clean']}% 的工作流通过 Graph Validator 零错误校验，"
            f"分支条件填写完整率 {sub['pct_conditions_filled']}%，返工语义说明完整率 {sub['pct_retry_semantics_filled']}%。"
        )
    if key == "extractability":
        return f"当前 {score} 分，节点与边的平均抽取置信度为 {sub['avg_confidence']}（1.0 为完全确定）。"
    if key == "authenticity":
        return (
            f"当前 {score} 分，{sub['pct_expert_confirmed_nodes']}% 的节点标记为专家已确认"
            f"（发布流程只收录 expert_confirmed 记录，通常接近 100%）；岗位、经验年限等专家背景字段尚未采集，不计入本次评分。"
        )
    if key == "annotation_readiness":
        return "当前 0 分：Gold 标注体系尚未实现（属于后续阶段范围），这个 0 分反映的是『体系缺失』而不是『数据本身质量差』，不应与其他维度同等解读。"
    if key == "diversity":
        return (
            f"当前 {score} 分，数据集里出现 {sub['distinct_roles']} 种岗位角色，"
            f"工作流长度标准差为 {sub['workflow_size_stddev']}，判断节点平均分支数 {sub['avg_decision_branches']}。"
        )
    if key == "structural_diversity":
        return (
            f"当前 {score} 分，Linear（无分支无并行）类型占比 {sub['pct_linear']}%，"
            f"含分支的占 {sub['pct_with_branch']}%，含并行的占 {sub['pct_with_parallel']}%，含返工路径的占 {sub['pct_with_retry']}%，例如 {example_text}。"
        )
    if key == "low_leakage_risk":
        return f"当前 {score} 分，触发描述完全重复的比例为 {sub['exact_duplicate_trigger_ratio']}%（更精细的近重复检测尚未实现，这是粗粒度信号）。"
    return f"当前 {score} 分。"


def explain_all(readiness: dict, workflows: list[dict]) -> dict[str, str]:
    return {key: explain_dimension(key, dim, workflows) for key, dim in readiness["dimensions"].items()}
