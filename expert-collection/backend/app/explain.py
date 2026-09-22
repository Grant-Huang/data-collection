"""Explanation Generator -- PRD 13.3.1/13.6/14.5/14.6: turns rule-computed statistics into a
plain-language narrative. IMPLEMENTATION_PLAN.md section 14, §15.2-①②③: calls a real LLM
through the `dashboard_explain`/`experiment_explain`/`experiment_compare_explain` slots when
configured, falling back to the original template generator (same pattern as
guide_service.py) on any failure -- not configured, network error, or the model's output
failing the anti-hallucination check below.

Honesty: every number in a generated explanation -- whether template or real model -- must be
traceable back to the statistics actually computed by quality.py/experiments.py. The template
path guarantees this by construction (it only ever prints numbers it was handed). The LLM
path cannot make that guarantee by construction, so `_no_fabricated_numbers` checks it after
the fact: any number in the model's output that doesn't appear anywhere in the source
statistics causes the whole response to be rejected and the caller falls back to the
template, rather than risk shipping a plausible-sounding but invented figure.
"""
from __future__ import annotations

import json
import re
from typing import Any

from . import llm_client
from . import settings as app_settings
from .quality import DIMENSION_LABELS


def _sample_names(workflows: list[dict], limit: int = 2) -> list[str]:
    return [w.get("name", w.get("id", "?")) for w in workflows[:limit]]


_NUMBER_RE = re.compile(r"-?\d+\.?\d*")
# Small integers are common in ordinary prose ("第1条", "两种情况" written as "2种") rather
# than a quoted statistic -- exempting them avoids rejecting harmless phrasing.
_EXEMPT_NUMBERS = {"0", "1", "2", "3"}


def _flatten_numbers(obj: Any) -> set[str]:
    """Every numeric value appearing anywhere in a nested stats dict/list, stringified in the
    same forms `_no_fabricated_numbers` might see quoted back (the raw value, and rounded to
    0-3 decimal places, since a model paraphrasing "0.8234" as "0.82" is still faithful).
    """
    out: set[str] = set()
    if isinstance(obj, dict):
        for v in obj.values():
            out |= _flatten_numbers(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= _flatten_numbers(v)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        out.add(str(obj))
        if isinstance(obj, float):
            for nd in range(4):
                out.add(str(round(obj, nd)))
    return out


def _no_fabricated_numbers(generated_text: str, source_stats: Any) -> bool:
    allowed = _flatten_numbers(source_stats) | _EXEMPT_NUMBERS
    return all(n in allowed for n in _NUMBER_RE.findall(generated_text))


def _llm_narrate(slot: str, system_prompt: str, user_payload: Any, source_stats: Any) -> str | None:
    """Returns the model's narrative, or None (caller falls back to the template) on any
    failure: slot not enabled/configured, the LLM call itself failing, an empty response, or
    a response that fails the anti-hallucination check.
    """
    slot_config = app_settings.resolve_slot_for_call(app_settings.get_effective_settings(), slot)
    if not (slot_config.get("enabled") and slot_config.get("endpoint") and slot_config.get("model_name")):
        return None
    try:
        result = llm_client.chat_completion(slot_config, [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ])
    except llm_client.LLMError:
        return None
    text = result.content.strip()
    if not text or not _no_fabricated_numbers(text, source_stats):
        return None
    return text


_DIMENSION_SYSTEM_PROMPT = """你是制造业数据集质量评分的解读助手。根据给定的统计数据，写一段中文说明，解释这个评分维度当前分数的依据。要求：
- 只能引用输入数据里出现过的数字，不能编造、四舍五入之外的换算或推算新的数字。
- 语气客观、简洁，一段话，不分点，不要有任何 markdown 格式。
- 只输出这段说明本身，不要有别的文字。"""


def explain_dimension(key: str, dim: dict[str, Any], workflows: list[dict]) -> str:
    label = DIMENSION_LABELS.get(key, key)
    if dim["score"] is None:
        return f"{label}：当前已确认记录数 {dim['sub_indicators']['sample_size']} 条，低于 {dim['sub_indicators']['threshold']} 条的最低统计门槛，暂不生成分数依据。"

    llm_text = _llm_narrate(
        "dashboard_explain", _DIMENSION_SYSTEM_PROMPT,
        {"dimension": label, "score": dim["score"], "sub_indicators": dim["sub_indicators"],
         "example_workflows": _sample_names(workflows)},
        dim,
    )
    if llm_text is not None:
        return llm_text
    return _template_explain_dimension(key, dim, workflows)


def _template_explain_dimension(key: str, dim: dict[str, Any], workflows: list[dict]) -> str:
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


_EXPERIMENT_SYSTEM_PROMPT = """你是制造业工作流抽取实验结果的解读助手。根据给定的实验指标和错误案例，写一段中文解读，说明这次实验结果说明了什么、可能的原因、以及建议。要求：
- 只能引用输入数据里出现过的数字，不能编造或推算新的数字。
- 可以分成"现象/可能原因/建议"这样的结构，但不要用 markdown 标题语法。
- 只输出解读本身，不要重复免责声明（免责声明由调用方统一加）。"""


def explain_experiment(metrics: dict, error_analysis: list[dict], train_count: int, test_count: int) -> str:
    """PRD 14.5: a plain-language read of one experiment's results. Every number is read
    straight from `metrics`/`error_analysis` -- no fabricated conclusions.
    """
    llm_text = _llm_narrate(
        "experiment_explain", _EXPERIMENT_SYSTEM_PROMPT,
        {"metrics": metrics, "error_analysis": error_analysis, "train_count": train_count, "test_count": test_count},
        {"metrics": metrics, "error_analysis": error_analysis, "train_count": train_count, "test_count": test_count},
    )
    if llm_text is not None:
        return llm_text + f"\n\n_{AI_GENERATED_DISCLOSURE}_"
    return _template_explain_experiment(metrics, error_analysis, train_count, test_count)


def _template_explain_experiment(metrics: dict, error_analysis: list[dict], train_count: int, test_count: int) -> str:
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


_COMPARISON_SYSTEM_PROMPT = """你是制造业工作流抽取实验对比结果的解读助手。根据给定的多个实验的指标（含已经算好的 precomputed_deltas 差值），以第一个为基准，写一段中文解读，说明其他实验相比基准好在哪、差在哪、可能为什么。要求：
- 数字直接引用 rows 或 precomputed_deltas 里已有的值，不要自己重新计算差值或编造新的数字。
- 只输出解读本身，不要重复免责声明（免责声明由调用方统一加）。"""


def explain_comparison(rows: list[dict]) -> str:
    """PRD 14.6: compares multiple experiments' metrics. `rows` is
    [{"name": str, "metrics": {...}}, ...]. Baseline is the first row.
    """
    if len(rows) < 2:
        return f"只选中了一个实验，没有可对比的对象。\n\n_{AI_GENERATED_DISCLOSURE}_"

    # Deltas are simple subtraction, not something the model should be trusted to compute
    # itself -- precomputing them and handing them over means the anti-hallucination check
    # (which only knows about raw input numbers) doesn't have to reject a legitimately
    # derived figure like "+0.17" just because it isn't literally present in `rows`.
    baseline = rows[0]
    deltas = []
    for other in rows[1:]:
        row_deltas = {
            key: round(other["metrics"][key] - baseline["metrics"][key], 3)
            for key in baseline["metrics"] if key in other["metrics"]
            and isinstance(baseline["metrics"][key], (int, float)) and isinstance(other["metrics"][key], (int, float))
        }
        deltas.append({"name": other["name"], "vs_baseline": baseline["name"], "deltas": row_deltas})
    payload = {"rows": rows, "baseline": baseline["name"], "precomputed_deltas": deltas}

    llm_text = _llm_narrate("experiment_compare_explain", _COMPARISON_SYSTEM_PROMPT, payload, payload)
    if llm_text is not None:
        return llm_text + f"\n\n_{AI_GENERATED_DISCLOSURE}_"
    return _template_explain_comparison(rows)


def _template_explain_comparison(rows: list[dict]) -> str:
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
