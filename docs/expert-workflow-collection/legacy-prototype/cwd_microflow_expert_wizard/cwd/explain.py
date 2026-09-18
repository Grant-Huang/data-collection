import os, json, pandas as pd

def rule_explain(df, lang="zh"):
    ok=df[df.get("status","ok")=="ok"].copy() if "status" in df else df.copy()
    if ok.empty:
        return "没有成功结果可解释。" if lang=="zh" else "No successful results to interpret."
    best=ok.loc[ok["f1"].idxmax()]
    if lang=="zh":
        parts=[f"当前最高 Micro-workflow F1 来自 **{best.get('label','当前设置')}**：{best['f1']:.3f}；Boundary F1={best['boundary_f1']:.3f}。"]
        emb=ok[ok["segmentation"]=="embedding_cp"] if "segmentation" in ok else pd.DataFrame()
        rule=ok[ok["segmentation"]=="heuristic"] if "segmentation" in ok else pd.DataFrame()
        if not emb.empty and not rule.empty:
            parts.append(f"Embedding 分段平均 Micro-workflow F1={emb['f1'].mean():.3f}，Rule-based={rule['f1'].mean():.3f}；该差异衡量更正式语义分段 baseline 的增益。")
        oracle=ok[ok["segmentation"]=="oracle"] if "segmentation" in ok else pd.DataFrame()
        if not oracle.empty and not emb.empty:
            parts.append(f"Oracle 与 Embedding 分段的 F1 gap={oracle['f1'].mean()-emb['f1'].mean():.3f}，代表当前 segmentation 仍存在的上限空间，不代表可部署性能。")
        parts.append("Synthetic ground truth 可以证明方法的恢复能力与消融关系，但不能单独证明真实 AgentNexus 环境中的外部有效性。")
        return "\n\n".join(parts)
    parts=[f"The highest Micro-workflow F1 is **{best.get('label','current setting')}** at {best['f1']:.3f}; Boundary F1={best['boundary_f1']:.3f}."]
    parts.append("Synthetic ground truth supports recovery and ablation claims, but cannot by itself establish external validity on real AgentNexus work.")
    return "\n\n".join(parts)

def llm_explain(df, lang="zh", model=None):
    key=os.getenv("OPENAI_API_KEY")
    if not key:
        return rule_explain(df,lang)
    try:
        from openai import OpenAI
        client=OpenAI(api_key=key)
        model=model or os.getenv("OPENAI_EXPLANATION_MODEL","gpt-5.6-luna")
        prompt=("用学术中文解释下面的实验结果。区分 segmentation 与 process miner 的贡献；"
                "Oracle只能作为upper bound；不要把synthetic结果外推为真实工业性能；最后指出最关键的下一步实验。"
                if lang=="zh" else
                "Interpret these experimental results academically. Separate contributions of segmentation and process miner; "
                "treat Oracle only as an upper bound; do not overgeneralize synthetic results; state the most important next experiments.")
        cols=[c for c in ["label","status","f1","boundary_f1","segmentation","miner","embedding_backend"] if c in df]
        r=client.responses.create(model=model,input=prompt+"\n"+json.dumps(df[cols].to_dict("records"),ensure_ascii=False))
        return r.output_text
    except Exception:
        return rule_explain(df,lang)
