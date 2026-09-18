from pathlib import Path
import sys, uuid, pandas as pd
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import streamlit as st

from cwd.experiment import run_pipeline
from cwd.advanced_experiments import (
    disturbance_ablation, robustness_curve,
    reusability_generalization, retrieval_utility_simulation,
    evaluate_expert_segmentation
)


LANG = st.sidebar.radio("Language / 语言", ["中文","English"], horizontal=True)
ZH = LANG=="中文"

T = {
"zh":{
"title":"协作工作流蒸馏 — 动态实验工作台",
"caption":"点击 ＋ 动态增加实验。实验卡固定宽度横向排列；超过屏幕宽度后可横向滚动。",
"add":"＋ 添加实验","runall":"▶ 运行全部实验","clear":"清空结果","remove":"× 删除",
"type":"实验类型","pipeline":"基础 Pipeline 对比","ablation":"干扰因素消融",
"robust":"鲁棒性曲线","reuse":"可复用性 / 泛化","utility":"Retrieval 使用价值",
"label":"实验名称","cases":"Cases","seed":"Seed","bv":"业务变体","ed":"执行偏差",
"le":"日志错误","human":"人工介入","hetero":"工具异构","semantic":"语义归一化",
"seg":"分段方法","miner":"Miner","backend":"Embedding","factor":"扫描因素",
"levels":"扫描水平","holdout":"Held-out 场景","tasks":"模拟任务数","guide":"Guidance quality",
"results":"实验结果","noexp":"至少保留一个实验。","running":"正在运行",
"boundary":"Exact Boundary F1","tol":"Tolerant Boundary F1 ±1","purity":"Segment Purity",
"frag":"Fragmentation","merge":"Merge Rate","micro":"Micro-workflow F1",
"note":"Retrieval Utility 是受控模拟实验，用于验证“复用指导是否可能产生价值”，不能作为真实 Agent 生产性能结论。",
},
"en":{
"title":"Collaborative Workflow Distillation — Dynamic Experiment Workbench",
"caption":"Use ＋ to add experiments dynamically. Fixed-width experiment cards are arranged horizontally and scroll when they exceed the viewport.",
"add":"＋ Add Experiment","runall":"▶ Run All Experiments","clear":"Clear Results","remove":"× Remove",
"type":"Experiment Type","pipeline":"Base Pipeline","ablation":"Disturbance Ablation",
"robust":"Robustness Curve","reuse":"Reusability / Generalization","utility":"Retrieval Utility",
"label":"Experiment Label","cases":"Cases","seed":"Seed","bv":"Business Variation","ed":"Execution Deviation",
"le":"Logging Error","human":"Human Intervention","hetero":"Tool Heterogeneity","semantic":"Semantic Normalization",
"seg":"Segmentation","miner":"Miner","backend":"Embedding","factor":"Sweep Factor",
"levels":"Sweep Levels","holdout":"Held-out Scenario","tasks":"Simulated Tasks","guide":"Guidance Quality",
"results":"Results","noexp":"Keep at least one experiment.","running":"Running",
"boundary":"Exact Boundary F1","tol":"Tolerant Boundary F1 ±1","purity":"Segment Purity",
"frag":"Fragmentation","merge":"Merge Rate","micro":"Micro-workflow F1",
"note":"Retrieval Utility is a controlled simulation of prospective reuse value; it is not evidence of real production-agent performance.",
}}
def tr(k): return T["zh" if ZH else "en"].get(k,k)

HELP={
"bv":("合理业务差异：可选步骤、合法重排、角色替代；不是日志错误。",
      "Legitimate variants such as optional steps, local reordering, and role substitution."),
"ed":("实际执行失败、重试、补偿或升级。","Execution failures, retries, compensation, or escalation."),
"le":("平台观测层的漏记、重复和时间戳扰动。","Missing, duplicate, or timestamp-perturbed log records."),
"seg":("把长 case 切成目标更一致的 work episodes。","Splits long cases into more coherent work episodes."),
"micro":("下游 micro-workflow 恢复的 Macro-F1。","Macro-F1 of downstream micro-workflow recovery."),
"boundary":("严格要求预测边界与真实 event 位置完全一致。","Requires an exact match to the ground-truth event boundary."),
"tol":("允许预测边界偏移 ±1 event，用于衡量 near-miss。","Allows a ±1 event offset to measure near-miss boundaries."),
"purity":("预测 episode 中属于同一 ground-truth microflow 的主导比例。","Dominant ground-truth microflow proportion inside a predicted episode."),
"frag":("一个真实 microflow 平均被切成多少预测片段；越接近1越好。","Average number of predicted segments overlapping one true microflow; 1 is ideal."),
"merge":("一个预测 episode 平均合并多少真实 microflows；越接近1越好。","Average number of true microflows merged into one predicted segment; 1 is ideal."),
}
def hp(k):
    pair=HELP.get(k)
    return pair[0] if ZH and pair else (pair[1] if pair else None)

# Fixed-width horizontal experiment strip.
st.markdown("""
<style>
.st-key-exp_strip [data-testid="stHorizontalBlock"] {
    display: flex !important;
    flex-wrap: nowrap !important;
    overflow-x: auto !important;
    overflow-y: hidden !important;
    gap: 12px !important;
    padding-bottom: 12px !important;
    align-items: flex-start !important;
}
.st-key-exp_strip [class*="st-key-exp_card_"] {
    flex: 0 0 300px !important;
    min-width: 300px !important;
    max-width: 300px !important;
}
.st-key-exp_strip [class*="st-key-exp_card_"] [data-testid="stVerticalBlock"] {
    gap: 0.45rem !important;
}
</style>
""", unsafe_allow_html=True)

st.title(tr("title"))
st.caption(tr("caption"))

# Expert datasets collected by the in-system Wizard are immediately available here.
if st.session_state.get("expert_datasets"):
    with st.expander("👩‍🏭 专家真实数据快速验证 / Expert Data Quick Validation", expanded=False):
        names=list(st.session_state.expert_datasets.keys())
        ds_name=st.selectbox("专家数据集", names, key="expert_quick_dataset")
        seg_method=st.selectbox("分段方法", ["heuristic","embedding_cp","graph_semantic","none","oracle"], index=1, key="expert_quick_seg")
        emb_backend=st.selectbox("Embedding backend", ["auto","tfidf_svd","sentence_transformer"], key="expert_quick_emb")
        ds=st.session_state.expert_datasets[ds_name]
        events=[]
        for case in ds.get("cases",{}).values(): events.extend(case.get("events",[]))
        st.caption(f"当前数据集：{len(ds.get('cases',{}))} 个完整案例，{len(events)} 个工作动作。")
        if st.button("运行专家分段验证", type="primary", key="run_expert_quick"):
            if events:
                er=evaluate_expert_segmentation(pd.DataFrame(events),segmentation=seg_method,embedding_backend=emb_backend)
                mm=er["metrics"]
                cols=st.columns(9)
                cols[0].metric("Exact Boundary F1",f"{mm.get('boundary_f1',0):.3f}")
                cols[1].metric("±1 F1",f"{mm.get('tolerant_boundary_f1@1',0):.3f}")
                cols[2].metric("±2 F1",f"{mm.get('tolerant_boundary_f1@2',0):.3f}")
                cols[3].metric("Purity",f"{mm.get('segment_purity',0):.3f}")
                cols[4].metric("Fragmentation",f"{mm.get('fragmentation',0):.2f}")
                cols[5].metric("Merge Rate",f"{mm.get('merge_rate',0):.2f}")
                cols[6].metric("Episode ARI",f"{mm.get('episode_ari',0):.3f}")
                cols[7].metric("Episode NMI",f"{mm.get('episode_nmi',0):.3f}")
                cols[8].metric("Pairwise F1",f"{mm.get('episode_pairwise_f1',0):.3f}")
                st.dataframe(er["data"][[c for c in ["case_id","step_no","raw_action_text","episode_name_expert","episode_pred"] if c in er["data"].columns]],use_container_width=True,hide_index=True)
            else:
                st.warning("该数据集还没有案例。")


def new_exp(i):
    return {"id":uuid.uuid4().hex[:8], "label":f"Experiment {i}"}

if "experiments" not in st.session_state:
    st.session_state.experiments=[new_exp(i) for i in range(1,5)]
if "experiment_results" not in st.session_state:
    st.session_state.experiment_results={}

top1,top2,top3,_=st.columns([1.2,1.5,1,6])
if top1.button(tr("add"), type="primary", use_container_width=True):
    st.session_state.experiments.append(new_exp(len(st.session_state.experiments)+1))
    st.rerun()
run_all=top2.button(tr("runall"), type="primary", use_container_width=True)
if top3.button(tr("clear"),use_container_width=True):
    st.session_state.experiment_results={}
    st.rerun()

type_options=[tr("pipeline"),tr("ablation"),tr("robust"),tr("reuse"),tr("utility")]
type_map={
    tr("pipeline"):"pipeline",tr("ablation"):"ablation",tr("robust"):"robustness",
    tr("reuse"):"reusability",tr("utility"):"utility"
}
seg_opts=["none","heuristic","embedding_cp","graph_semantic","oracle"]
miner_opts=["consensus_dfg","consensus_dependency_graph","pm4py_inductive","pm4py_heuristics"]

configs=[]
remove_id=None

# Streamlit >= 1.45 supports horizontal containers.
try:
    strip=st.container(horizontal=True, key="exp_strip")
except TypeError:
    strip=st.container(key="exp_strip")

with strip:
    for idx,ex in enumerate(st.session_state.experiments):
        with st.container(border=True, key=f"exp_card_{ex['id']}"):
            c1,c2=st.columns([4,1])
            label=c1.text_input(tr("label"),ex.get("label",f"Experiment {idx+1}"),
                                key=f"label_{ex['id']}",label_visibility="collapsed")
            if c2.button("×",key=f"rm_{ex['id']}",help=tr("remove")):
                remove_id=ex["id"]

            default_type=type_options[min(idx,len(type_options)-1)]
            et_ui=st.selectbox(tr("type"),type_options,
                               index=type_options.index(ex.get("type_ui",default_type)) if ex.get("type_ui",default_type) in type_options else 0,
                               key=f"type_{ex['id']}")
            et=type_map[et_ui]

            n_cases=st.number_input(tr("cases"),50,10000,
                int(ex.get("n_cases",300)),50,key=f"cases_{ex['id']}")
            seed=st.number_input(tr("seed"),1,999999,
                int(ex.get("seed",42)),key=f"seed_{ex['id']}")

            cfg={"id":ex["id"],"label":label,"type":et,
                 "n_cases":int(n_cases),"seed":int(seed)}

            if et in ("pipeline","ablation","robustness","reusability"):
                bv=st.slider(tr("bv"),0.0,0.40,float(ex.get("bv",.10)),.01,
                             key=f"bv_{ex['id']}",help=hp("bv"))
                ed=st.slider(tr("ed"),0.0,0.40,float(ex.get("ed",.08)),.01,
                             key=f"ed_{ex['id']}",help=hp("ed"))
                le=st.slider(tr("le"),0.0,0.20,float(ex.get("le",.03)),.01,
                             key=f"le_{ex['id']}",help=hp("le"))
                human=st.slider(tr("human"),0.0,0.40,float(ex.get("human",.15)),.05,
                                key=f"human_{ex['id']}")
                hetero=st.slider(tr("hetero"),1,3,int(ex.get("hetero",3)),
                                 key=f"het_{ex['id']}")
                seg=st.selectbox(tr("seg"),seg_opts,
                    index=seg_opts.index(ex.get("seg","embedding_cp")),
                    key=f"seg_{ex['id']}",help=hp("seg"))
                miner=st.selectbox(tr("miner"),miner_opts,
                    index=miner_opts.index(ex.get("miner","consensus_dependency_graph")),
                    key=f"miner_{ex['id']}")
                backend=st.selectbox(tr("backend"),["auto","tfidf_svd","sentence_transformer"],
                    index=["auto","tfidf_svd","sentence_transformer"].index(ex.get("backend","auto")),
                    key=f"backend_{ex['id']}")
                semantic=st.checkbox(tr("semantic"),bool(ex.get("semantic",True)),
                                     key=f"sem_{ex['id']}")
                cfg.update(bv=bv,ed=ed,le=le,human=human,hetero=hetero,
                           seg=seg,miner=miner,backend=backend,semantic=semantic)

            if et=="robustness":
                factors=["logging_error_rate","business_variation_rate","execution_deviation_rate"]
                factor=st.selectbox(tr("factor"),factors,key=f"factor_{ex['id']}")
                levels=st.text_input(tr("levels"),"0,.03,.05,.10,.15",key=f"levels_{ex['id']}")
                cfg.update(factor=factor,levels=levels)

            if et=="reusability":
                holdouts=list(__import__("cwd.catalog",fromlist=["SCENARIOS"]).SCENARIOS.keys())
                holdout=st.selectbox(tr("holdout"),holdouts,index=len(holdouts)-1,key=f"hold_{ex['id']}")
                cfg["holdout"]=holdout

            if et=="utility":
                tasks=st.number_input(tr("tasks"),100,10000,int(ex.get("tasks",500)),100,key=f"tasks_{ex['id']}")
                guide=st.slider(tr("guide"),0.0,1.0,float(ex.get("guide",.85)),.05,key=f"guide_{ex['id']}")
                cfg.update(tasks=int(tasks),guide=guide)

            configs.append(cfg)
            ex.update({
                "label":label,"type_ui":et_ui,"n_cases":int(n_cases),"seed":int(seed),
                **{k:v for k,v in cfg.items() if k not in ("id","label","type")}
            })

if remove_id:
    if len(st.session_state.experiments)>1:
        st.session_state.experiments=[x for x in st.session_state.experiments if x["id"]!=remove_id]
        st.session_state.experiment_results.pop(remove_id,None)
        st.rerun()
    else:
        st.warning(tr("noexp"))

def run_cfg(cfg):
    common=dict(
        n_cases=cfg.get("n_cases",300),seed=cfg.get("seed",42),
        business_variation_rate=cfg.get("bv",.10),
        execution_deviation_rate=cfg.get("ed",.08),
        logging_error_rate=cfg.get("le",.03),
        tool_heterogeneity=cfg.get("hetero",3),
        human_variant_rate=cfg.get("human",.15),
        segmentation=cfg.get("seg","embedding_cp"),
        miner=cfg.get("miner","consensus_dfg"),
        semantic_normalization=cfg.get("semantic",True),
        embedding_backend=cfg.get("backend","auto"),
    )
    if cfg["type"]=="pipeline":
        r=run_pipeline(**common)
        s={**r["classification"],**r["segmentation"],**r["complexity"],**r.get("graph_recovery",{})}
        return {"kind":"single","summary":pd.DataFrame([s]),"raw":r}
    if cfg["type"]=="ablation":
        df=disturbance_ablation(**common)
        return {"kind":"table","summary":df}
    if cfg["type"]=="robustness":
        levels=[float(x.strip()) for x in cfg["levels"].split(",") if x.strip()]
        df=robustness_curve(
            factor=cfg["factor"],levels=levels,n_cases=common["n_cases"],seed=common["seed"],
            segmentation=common["segmentation"],miner=common["miner"],
            semantic_normalization=common["semantic_normalization"],
            tool_heterogeneity=common["tool_heterogeneity"],
            human_variant_rate=common["human_variant_rate"],
            base_bv=common["business_variation_rate"],
            base_ed=common["execution_deviation_rate"],
            base_le=common["logging_error_rate"],
            embedding_backend=common["embedding_backend"])
        return {"kind":"curve","summary":df}
    if cfg["type"]=="reusability":
        d=reusability_generalization(
            n_cases=common["n_cases"],seed=common["seed"],holdout_scenario=cfg["holdout"],
            segmentation=common["segmentation"],miner=common["miner"],
            semantic_normalization=common["semantic_normalization"],
            tool_heterogeneity=common["tool_heterogeneity"],
            human_variant_rate=common["human_variant_rate"],
            business_variation_rate=common["business_variation_rate"],
            execution_deviation_rate=common["execution_deviation_rate"],
            logging_error_rate=common["logging_error_rate"],
            embedding_backend=common["embedding_backend"])
        return {"kind":"reuse","summary":d["summary"],"detail":d["workflow_stats"]}
    if cfg["type"]=="utility":
        df=retrieval_utility_simulation(
            n_tasks=cfg["tasks"],seed=cfg["seed"],guidance_quality=cfg["guide"])
        return {"kind":"utility","summary":df}
    raise ValueError(cfg["type"])

if run_all:
    for cfg in configs:
        try:
            with st.spinner(f"{tr('running')}: {cfg['label']}"):
                st.session_state.experiment_results[cfg["id"]]={"ok":True,"label":cfg["label"],"type":cfg["type"],"data":run_cfg(cfg)}
        except Exception as e:
            st.session_state.experiment_results[cfg["id"]]={"ok":False,"label":cfg["label"],"type":cfg["type"],"error":str(e)}

st.divider()
st.header(tr("results"))

# Cross-experiment headline comparison for simple pipeline experiments.
headline=[]
for cfg in configs:
    rr=st.session_state.experiment_results.get(cfg["id"])
    if rr and rr.get("ok") and rr["data"]["kind"]=="single":
        s=rr["data"]["summary"].iloc[0]
        headline.append({"Experiment":cfg["label"],
                         tr("micro"):s.get("f1"),
                         tr("boundary"):s.get("boundary_f1"),
                         tr("tol"):s.get("tolerant_boundary_f1@1"),
                         tr("purity"):s.get("segment_purity"),
                         tr("frag"):s.get("fragmentation"),
                         tr("merge"):s.get("merge_rate")})
if headline:
    hdf=pd.DataFrame(headline).set_index("Experiment")
    st.dataframe(hdf.round(4),use_container_width=True)
    c1,c2=st.columns(2)
    with c1:
        st.bar_chart(hdf[[tr("micro"),tr("boundary"),tr("tol")]])
    with c2:
        st.bar_chart(hdf[[tr("purity"),tr("frag"),tr("merge")]])

for cfg in configs:
    rr=st.session_state.experiment_results.get(cfg["id"])
    if not rr: continue
    with st.expander(cfg["label"],expanded=True):
        if not rr.get("ok"):
            st.error(rr.get("error"))
            continue
        data=rr["data"]; df=data["summary"]
        st.dataframe(df.round(4),use_container_width=True)
        if data["kind"]=="table":
            chart_cols=[c for c in ["f1","boundary_f1","marginal_f1_drop"] if c in df]
            if chart_cols:
                st.bar_chart(df.set_index("condition")[chart_cols])
        elif data["kind"]=="curve":
            st.line_chart(df.set_index("level")[[c for c in ["f1","boundary_f1","tolerant_f1@1","segment_purity"] if c in df]])
        elif data["kind"]=="reuse":
            if not data["detail"].empty:
                st.subheader("Micro-workflow reuse detail")
                st.dataframe(data["detail"].round(4),use_container_width=True)
                st.bar_chart(data["detail"].set_index("microflow")[["case_support","scenario_breadth","reuse_diversity"]])
        elif data["kind"]=="utility":
            st.warning(tr("note"))
            st.bar_chart(df.set_index("condition")[["task_success_rate"]])
            st.bar_chart(df.set_index("condition")[["avg_steps","avg_tool_calls","avg_human_interventions"]])
