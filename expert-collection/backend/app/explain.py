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


# PRD 14.5.2's disclosure line -- must be shown wherever a generated explanation is shown.
AI_GENERATED_DISCLOSURE = "以上解读由 AI 根据本次实验指标自动生成，请结合下方明细数据核实。"


def explain_experiment(metrics: dict, error_analysis: list[dict], train_count: int, test_count: int) -> str:
    """PRD 14.5: a plain-language read of one experiment's results. Every number is read
    straight from `metrics`/`error_analysis` -- no fabricated conclusions.
    """
    node_f1 = metrics["node_f1"]
    edge_f1 = metrics["edge_f1"]
    match_rate = metrics["structural_match_rate"]

    if node_f1 >= 0.8:
        node_verdict = "在主干节点类型识别上表现良好"
    elif node_f1 >= 0.6:
        node_verdict = "在主干节点类型识别上表现中等"
    else:
        node_verdict = "在主干节点类型识别上偏弱"

    summary = (
        f"本次实验用训练集（{train_count} 条）里最具代表性的一条主路径作为共识结构，拿测试集（{test_count} 条）逐条比对："
        f"{node_verdict}（Node F1 {node_f1}），结构顺序匹配度（Edge/Bigram F1）为 {edge_f1}，"
        f"结构特征（是否含分支/并行/返工）的匹配率为 {match_rate}。"
    )

    points = []
    if error_analysis:
        groups: dict[str, int] = {}
        for case in error_analysis:
            groups[case["group"]] = groups.get(case["group"], 0) + 1
        worst = max(groups, key=lambda g: groups[g])
        points.append(
            f"**现象** → 测试集中有 {len(error_analysis)} 条工作流与共识结构的匹配度较低（Node F1 或 Edge F1 < 0.6），"
            f"其中『{worst}』类型的工作流最多（{groups[worst]} 条）。 **可能原因** → 训练集的共识结构是从单一代表性样本得出的简单主路径，"
            f"天然无法覆盖训练集里没有充分出现的结构变体。 **建议** → 扩大训练集规模，或改用能识别分支/并行子结构的方法（本轮 `consensus_dfg` 只挖主路径）。"
        )
    else:
        points.append("**现象** → 测试集所有工作流都与共识结构匹配良好。 **可能原因** → 数据集里工作流的结构模式比较集中、变体不多。 **建议** → 可以尝试引入更多样化的工作流样本，观察分数是否会下降。")

    if edge_f1 < node_f1 - 0.15:
        points.append(
            f"**现象** → 结构顺序匹配度（{edge_f1}）明显低于节点类型匹配度（{node_f1}）。 "
            f"**可能原因** → 测试集里的工作流虽然用了相似的步骤类型，但先后顺序跟训练集的共识结构不一致。 "
            f"**建议** → 检查这批工作流是不是记录了同一类工作的不同做法，如果是，说明这类工作本身就有多种合理顺序，不算方法的缺陷。"
        )

    return summary + "\n\n" + "\n\n".join(points) + f"\n\n_{AI_GENERATED_DISCLOSURE}_"


def explain_comparison(rows: list[dict]) -> str:
    """PRD 14.6: compares multiple experiments' metrics. `rows` is
    [{"name": str, "metrics": {...}}, ...]. Baseline is the first row.
    """
    if len(rows) < 2:
        return f"只选中了一个实验，没有可对比的对象。\n\n_{AI_GENERATED_DISCLOSURE}_"

    baseline = rows[0]
    lines = []
    for other in rows[1:]:
        diffs = []
        for key, label in (("node_f1", "Node F1"), ("edge_f1", "Edge F1"), ("structural_match_rate", "结构匹配率")):
            b, o = baseline["metrics"].get(key), other["metrics"].get(key)
            if b is None or o is None:
                continue
            delta = round(o - b, 3)
            if abs(delta) < 0.01:
                continue
            direction = "提升" if delta > 0 else "下降"
            diffs.append(f"{label} 从 {b} {direction}到 {o}（{'+' if delta>0 else ''}{delta}）")
        if diffs:
            lines.append(f"**{other['name']}** 相比 **{baseline['name']}**（基准）：{'；'.join(diffs)}。")
        else:
            lines.append(f"**{other['name']}** 与 **{baseline['name']}**（基准）相比，各项指标差异都小于 0.01，基本持平。")

    return "\n\n".join(lines) + f"\n\n_{AI_GENERATED_DISCLOSURE}_"
