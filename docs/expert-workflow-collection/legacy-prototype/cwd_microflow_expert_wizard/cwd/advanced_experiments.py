from typing import Dict, List, Tuple
import random, math
import numpy as np
import pandas as pd
from .generator import generate_dataset
from .experiment import run_pipeline, run_pipeline_on_dataframe
from .catalog import MICROFLOWS, SCENARIOS

def disturbance_ablation(
    n_cases=500, seed=42, segmentation="embedding_cp", miner="consensus_dfg",
    semantic_normalization=True, tool_heterogeneity=3, human_variant_rate=.15,
    business_variation_rate=.10, execution_deviation_rate=.08, logging_error_rate=.03,
    embedding_backend="auto"
) -> pd.DataFrame:
    settings=[
        ("Clean",0.0,0.0,0.0),
        ("Business variation only",business_variation_rate,0.0,0.0),
        ("Execution deviation only",0.0,execution_deviation_rate,0.0),
        ("Logging error only",0.0,0.0,logging_error_rate),
        ("Combined",business_variation_rate,execution_deviation_rate,logging_error_rate),
    ]
    rows=[]
    clean_f1=None
    for label,bv,ed,le in settings:
        r=run_pipeline(
            n_cases=n_cases,business_variation_rate=bv,
            execution_deviation_rate=ed,logging_error_rate=le,
            tool_heterogeneity=tool_heterogeneity,human_variant_rate=human_variant_rate,
            seed=seed,semantic_normalization=semantic_normalization,
            segmentation=segmentation,miner=miner,embedding_backend=embedding_backend
        )
        f1=r["classification"]["f1"]
        if label=="Clean": clean_f1=f1
        rows.append({
            "condition":label,"business_variation_rate":bv,
            "execution_deviation_rate":ed,"logging_error_rate":le,
            "f1":f1,"boundary_f1":r["segmentation"]["boundary_f1"],
            "tolerant_f1@1":r["segmentation"]["tolerant_boundary_f1@1"],
            "segment_purity":r["segmentation"]["segment_purity"],
            "fragmentation":r["segmentation"]["fragmentation"],
            "merge_rate":r["segmentation"]["merge_rate"],
        })
    df=pd.DataFrame(rows)
    if clean_f1 is not None:
        df["marginal_f1_drop"]=clean_f1-df["f1"]
    return df

def robustness_curve(
    factor: str="logging_error_rate",
    levels: List[float]=None,
    n_cases=500, seed=42,
    segmentation="embedding_cp", miner="consensus_dfg",
    semantic_normalization=True, tool_heterogeneity=3, human_variant_rate=.15,
    base_bv=.10, base_ed=.08, base_le=.03, embedding_backend="auto"
) -> pd.DataFrame:
    if levels is None:
        levels=[0,.03,.05,.10,.15]
    rows=[]
    for level in levels:
        pars={"business_variation_rate":base_bv,
              "execution_deviation_rate":base_ed,
              "logging_error_rate":base_le}
        pars[factor]=float(level)
        r=run_pipeline(
            n_cases=n_cases,seed=seed,
            semantic_normalization=semantic_normalization,
            segmentation=segmentation,miner=miner,
            tool_heterogeneity=tool_heterogeneity,human_variant_rate=human_variant_rate,
            embedding_backend=embedding_backend,**pars
        )
        rows.append({
            "factor":factor,"level":float(level),
            "f1":r["classification"]["f1"],
            "boundary_f1":r["segmentation"]["boundary_f1"],
            "tolerant_f1@1":r["segmentation"]["tolerant_boundary_f1@1"],
            "segment_purity":r["segmentation"]["segment_purity"],
            "fragmentation":r["segmentation"]["fragmentation"],
            "merge_rate":r["segmentation"]["merge_rate"],
        })
    return pd.DataFrame(rows)

def reusability_generalization(
    n_cases=1500, seed=42, holdout_scenario="S5_complex_cross_functional",
    segmentation="oracle", miner="consensus_dfg",
    semantic_normalization=True, tool_heterogeneity=3, human_variant_rate=.15,
    business_variation_rate=.10, execution_deviation_rate=.08, logging_error_rate=.03,
    embedding_backend="auto"
) -> Dict:
    """
    Train discovery on all scenarios except one held-out composition.
    Test whether discovered micro-workflow identities cover the held-out scenario.
    """
    raw=generate_dataset(
        n_cases=n_cases,business_variation_rate=business_variation_rate,
        execution_deviation_rate=execution_deviation_rate,logging_error_rate=logging_error_rate,
        tool_heterogeneity=tool_heterogeneity,human_variant_rate=human_variant_rate,seed=seed
    )
    train=raw[raw["scenario"]!=holdout_scenario].copy()
    test=raw[raw["scenario"]==holdout_scenario].copy()
    if train.empty or test.empty:
        return {"summary":pd.DataFrame(), "workflow_stats":pd.DataFrame()}

    tr=run_pipeline_on_dataframe(
        train,seed=seed,semantic_normalization=semantic_normalization,
        segmentation=segmentation,miner=miner,embedding_backend=embedding_backend
    )
    discovered_ids=set(tr["mapping"].values())

    # Reuse statistics based on train GT labels, only used for experimental evaluation.
    wf_rows=[]
    train_cases=train[["case_id","scenario","microflow_gt"]].drop_duplicates()
    total_cases=train["case_id"].nunique()
    scenario_count=train["scenario"].nunique()
    for mw in sorted(MICROFLOWS):
        sub=train_cases[train_cases["microflow_gt"]==mw]
        support=sub["case_id"].nunique()/total_cases if total_cases else 0
        counts=sub["scenario"].value_counts()
        probs=(counts/counts.sum()).values if counts.sum() else np.array([])
        entropy=float(-sum(p*math.log(p) for p in probs if p>0))
        max_entropy=math.log(scenario_count) if scenario_count>1 else 1
        diversity=entropy/max_entropy if max_entropy>0 else 0
        wf_rows.append({
            "microflow":mw,
            "discovered_in_train":mw in discovered_ids,
            "case_support":support,
            "scenario_breadth":sub["scenario"].nunique()/scenario_count if scenario_count else 0,
            "reuse_diversity":diversity,
        })
    wf_stats=pd.DataFrame(wf_rows)

    test_relevant=test.copy()
    event_coverage=float(test_relevant["microflow_gt"].isin(discovered_ids).mean()) if len(test_relevant) else 0
    gt_test_ids=set(test_relevant["microflow_gt"].unique())
    composition_coverage=len(gt_test_ids & discovered_ids)/len(gt_test_ids) if gt_test_ids else 0

    return {
        "summary":pd.DataFrame([{
            "heldout_scenario":holdout_scenario,
            "train_cases":train["case_id"].nunique(),
            "test_cases":test["case_id"].nunique(),
            "discovered_microflows":len(discovered_ids),
            "heldout_event_reuse_coverage":event_coverage,
            "heldout_microflow_composition_coverage":composition_coverage,
            "train_microflow_f1":tr["classification"]["f1"],
        }]),
        "workflow_stats":wf_stats,
    }

def retrieval_utility_simulation(
    n_tasks=500, seed=42, guidance_quality=.85,
    base_error_rate=.18, irrelevant_action_rate=.20,
    human_escalation_rate=.15
) -> pd.DataFrame:
    """
    Lightweight prospective utility simulation.
    A task requires the steps of one ground-truth micro-workflow.
    Without guidance, the executor may skip, retry, or insert irrelevant actions.
    With a retrieved micro-workflow, these probabilities are reduced according to
    guidance_quality. This is a controlled utility experiment, not evidence of real
    production-agent performance.
    """
    rng=random.Random(seed)
    rows=[]
    mw_ids=list(MICROFLOWS)
    for condition in ["without_microflow","with_retrieved_microflow"]:
        for task_id in range(n_tasks):
            mw=MICROFLOWS[rng.choice(mw_ids)]
            required=[s.capability for s in mw.steps]
            error=base_error_rate
            irrelevant=irrelevant_action_rate
            escalation=human_escalation_rate
            if condition=="with_retrieved_microflow":
                error *= (1-guidance_quality*.65)
                irrelevant *= (1-guidance_quality*.70)
                escalation *= (1-guidance_quality*.35)

            completed=0
            steps=0
            tool_calls=0
            human_calls=0
            for cap in required:
                if rng.random()<irrelevant:
                    steps+=1; tool_calls+=1
                if rng.random()<error:
                    # retry/failure; may still recover
                    steps+=1; tool_calls+=1
                    if rng.random()<.25:
                        continue
                steps+=1; tool_calls+=1; completed+=1
                if rng.random()<escalation:
                    human_calls+=1; steps+=1
            success=int(completed==len(required))
            rows.append({
                "condition":condition,"task_id":task_id,"microflow":mw.microflow_id,
                "success":success,"steps":steps,"tool_calls":tool_calls,
                "human_interventions":human_calls
            })
    raw=pd.DataFrame(rows)
    summary=raw.groupby("condition").agg(
        task_success_rate=("success","mean"),
        avg_steps=("steps","mean"),
        avg_tool_calls=("tool_calls","mean"),
        avg_human_interventions=("human_interventions","mean"),
    ).reset_index()
    return summary

def evaluate_expert_segmentation(events_df, segmentation="embedding_cp", embedding_backend="auto", seed=42):
    """Evaluate episode segmentation against expert-annotated reference boundaries.
    This deliberately does not compute micro-workflow F1 because expert workflow labels
    are open-vocabulary and should not be forced into the synthetic MICROFLOWS catalog.
    """
    import pandas as pd
    from .segmentation import no_segmentation, heuristic_segmentation, embedding_change_point_segmentation, oracle_segmentation, dependency_semantic_segmentation
    from .evaluation import segmentation_metrics, tolerant_boundary_metrics, segmentation_structure_metrics, window_diff_score, episode_membership_metrics

    df=events_df.copy()
    if df.empty:
        return {"data":df,"metrics":{}}
    # Canonicalize expert-wizard fields into the observable trace schema.
    df["timestamp"] = pd.to_datetime(df.get("timestamp_raw", pd.Series(range(len(df)))), errors="coerce")
    # deterministic fallback ordering for missing times
    missing=df["timestamp"].isna()
    base=pd.Timestamp("2026-01-01")
    df.loc[missing,"timestamp"]=[base+pd.Timedelta(seconds=int(x)) for x in df.loc[missing,"step_no"]]
    df["capability"] = df.get("raw_action_text", "").astype(str)
    df["activity"] = df["capability"]
    df["intent"] = df.get("raw_intent_text", "").astype(str)
    df["actor_role"] = df.get("role_raw", "").astype(str)
    df["actor_type"] = df.get("actor_type", "").replace("", pd.NA)
    if df["actor_type"].isna().any():
        def infer_actor(row):
            t=(str(row.get("actor_raw",""))+" "+str(row.get("role_raw",""))).lower()
            return "agent" if "agent" in t or "助手" in t else "human"
        df["actor_type"]=[infer_actor(r) if pd.isna(a) else a for (_,r),a in zip(df.iterrows(),df["actor_type"])]
    df["object_type"] = df.get("raw_object_text", "").astype(str)
    df["status"] = df.get("execution_flag", "否").map(lambda x: "deviation" if str(x)=="是" else "success")
    df["action_type"] = "work"
    df["episode_id_gt"] = df.get("episode_id_expert", "").astype(str)
    # open-vocabulary expert episode name is used only for purity here
    df["microflow_gt"] = df.get("episode_name_expert", "").astype(str)

    if segmentation=="none":
        pred=no_segmentation(df)
    elif segmentation=="heuristic":
        pred=heuristic_segmentation(df)
    elif segmentation=="embedding_cp":
        pred=embedding_change_point_segmentation(df,backend=embedding_backend,random_state=seed)
    elif segmentation=="graph_semantic":
        pred=dependency_semantic_segmentation(df)
    elif segmentation=="oracle":
        pred=oracle_segmentation(df)
    else:
        raise ValueError(segmentation)

    m={}
    m.update(segmentation_metrics(pred))
    m.update(episode_membership_metrics(pred))
    m.update(tolerant_boundary_metrics(pred,1))
    m.update(tolerant_boundary_metrics(pred,2))
    m.update(segmentation_structure_metrics(pred))
    m["window_diff"]=window_diff_score(pred,4)
    m["cases"]=int(pred["case_id"].nunique())
    m["events"]=int(len(pred))
    return {"data":pred,"metrics":m}
