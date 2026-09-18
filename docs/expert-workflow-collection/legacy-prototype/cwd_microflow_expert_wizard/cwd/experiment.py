from typing import Dict
import pandas as pd
from .generator import generate_dataset
from .semantics import normalize_events
from .segmentation import (
    oracle_segmentation, heuristic_segmentation, no_segmentation,
    embedding_change_point_segmentation, dependency_semantic_segmentation
)
from .mining import episode_table, cluster_episodes, mine_cluster_workflows
from .evaluation import (
    match_workflows, microflow_classification_metrics,
    segmentation_metrics, model_complexity,
    tolerant_boundary_metrics, segmentation_structure_metrics,
    window_diff_score, episode_membership_metrics
)

def run_pipeline(
    n_cases: int = 500,
    business_variation_rate: float = 0.10,
    execution_deviation_rate: float = 0.08,
    logging_error_rate: float = 0.03,
    tool_heterogeneity: int = 3,
    human_variant_rate: float = 0.15,
    seed: int = 42,
    semantic_normalization: bool = True,
    segmentation: str = "embedding_cp",
    miner: str = "consensus_dependency_graph",
    n_clusters: int = 8,
    embedding_backend: str = "auto",
    embedding_model: str = "all-MiniLM-L6-v2",
    cp_window: int = 2,
    cp_quantile: float = 0.70,
    min_segment_events: int = 2,
    inductive_noise_threshold: float = 0.0,
    heuristics_dependency_threshold: float = 0.5,
) -> Dict:
    raw = generate_dataset(
        n_cases=n_cases,
        business_variation_rate=business_variation_rate,
        execution_deviation_rate=execution_deviation_rate,
        logging_error_rate=logging_error_rate,
        tool_heterogeneity=tool_heterogeneity,
        human_variant_rate=human_variant_rate,
        seed=seed,
    )
    return run_pipeline_on_dataframe(
        raw, seed=seed,
        semantic_normalization=semantic_normalization,
        segmentation=segmentation, miner=miner, n_clusters=n_clusters,
        embedding_backend=embedding_backend, embedding_model=embedding_model,
        cp_window=cp_window, cp_quantile=cp_quantile,
        min_segment_events=min_segment_events,
        inductive_noise_threshold=inductive_noise_threshold,
        heuristics_dependency_threshold=heuristics_dependency_threshold,
    )

def run_pipeline_on_dataframe(
    raw: pd.DataFrame,
    seed: int = 42,
    semantic_normalization: bool = True,
    segmentation: str = "embedding_cp",
    miner: str = "consensus_dependency_graph",
    n_clusters: int = 8,
    embedding_backend: str = "auto",
    embedding_model: str = "all-MiniLM-L6-v2",
    cp_window: int = 2,
    cp_quantile: float = 0.70,
    min_segment_events: int = 2,
    inductive_noise_threshold: float = 0.0,
    heuristics_dependency_threshold: float = 0.5,
) -> Dict:
    data = normalize_events(raw, use_semantics=semantic_normalization)
    if segmentation == "oracle":
        data = oracle_segmentation(data)
    elif segmentation == "none":
        data = no_segmentation(data)
    elif segmentation == "heuristic":
        data = heuristic_segmentation(data)
    elif segmentation == "graph_semantic":
        data = dependency_semantic_segmentation(data)
    elif segmentation == "embedding_cp":
        data = embedding_change_point_segmentation(
            data, model_name=embedding_model, window=cp_window,
            threshold_quantile=cp_quantile,
            min_segment_events=min_segment_events,
            backend=embedding_backend, random_state=seed
        )
    else:
        raise ValueError("segmentation must be: none, heuristic, embedding_cp, graph_semantic, oracle")

    episodes = episode_table(data)
    clustered, cl_meta = cluster_episodes(episodes, n_clusters=n_clusters, random_state=seed)
    workflows = mine_cluster_workflows(
        clustered, miner=miner,
        inductive_noise_threshold=inductive_noise_threshold,
        heuristics_dependency_threshold=heuristics_dependency_threshold
    )
    matches, mapping = match_workflows(workflows)
    cls = microflow_classification_metrics(clustered, mapping)
    seg = segmentation_metrics(data)
    seg.update(episode_membership_metrics(data))
    seg.update(tolerant_boundary_metrics(data,1))
    seg.update(tolerant_boundary_metrics(data,2))
    seg.update(segmentation_structure_metrics(data))
    seg["window_diff"] = window_diff_score(data,4)
    complexity = model_complexity(workflows)
    graph_recovery = {}
    if not matches.empty:
        for col in ["node_f1","edge_f1","fork_f1","join_f1","branch_type_accuracy","structural_similarity"]:
            if col in matches.columns:
                graph_recovery[col] = float(matches[col].dropna().mean()) if matches[col].notna().any() else float("nan")
    backend_used = None
    if "embedding_backend" in data.columns and len(data):
        backend_used = data["embedding_backend"].mode().iloc[0]
    return {
        "raw":raw, "data":data, "episodes":episodes, "clustered":clustered,
        "workflows":workflows, "matches":matches, "mapping":mapping,
        "classification":cls, "segmentation":seg, "complexity":complexity, "graph_recovery":graph_recovery,
        "silhouette":cl_meta["silhouette"],
        "embedding_backend_used":backend_used, "miner":miner,
    }

def paper_baseline_matrix(
    n_cases=500,
    business_variation_rate=.10,
    execution_deviation_rate=.08,
    logging_error_rate=.03,
    tool_heterogeneity=3,
    human_variant_rate=.15,
    seeds=(11,22,33,44,55),
    embedding_backend="auto",
):
    configs = [
        ("Raw + No Seg + Consensus DFG", False, "none", "consensus_dfg"),
        ("Semantic + No Seg + Consensus DFG", True, "none", "consensus_dfg"),
        ("Semantic + Rule Seg + Consensus DFG", True, "heuristic", "consensus_dfg"),
        ("Semantic + Embedding CP + Consensus DFG", True, "embedding_cp", "consensus_dfg"),
        ("Semantic + Embedding CP + Dependency Graph", True, "embedding_cp", "consensus_dependency_graph"),
        ("Semantic + Graph Semantic Seg + Dependency Graph", True, "graph_semantic", "consensus_dependency_graph"),
        ("Semantic + Embedding CP + Inductive Miner", True, "embedding_cp", "pm4py_inductive"),
        ("Semantic + Embedding CP + Heuristics Miner", True, "embedding_cp", "pm4py_heuristics"),
        ("Oracle + Dependency Graph", True, "oracle", "consensus_dependency_graph"),
        ("Oracle + Inductive Miner", True, "oracle", "pm4py_inductive"),
        ("Oracle + Heuristics Miner", True, "oracle", "pm4py_heuristics"),
    ]
    rows=[]
    for seed in seeds:
        for label, sem, seg, miner in configs:
            try:
                res=run_pipeline(
                    n_cases=n_cases,
                    business_variation_rate=business_variation_rate,
                    execution_deviation_rate=execution_deviation_rate,
                    logging_error_rate=logging_error_rate,
                    tool_heterogeneity=tool_heterogeneity,
                    human_variant_rate=human_variant_rate,
                    seed=seed, semantic_normalization=sem,
                    segmentation=seg, miner=miner,
                    embedding_backend=embedding_backend
                )
                rows.append({
                    "seed":seed, "label":label, "status":"ok",
                    "semantic_normalization":sem,
                    "segmentation":seg, "miner":miner,
                    "embedding_backend":res["embedding_backend_used"],
                    **res["classification"], **res["segmentation"],
                    **res["complexity"], **res.get("graph_recovery",{}), "silhouette":res["silhouette"]
                })
            except Exception as e:
                rows.append({
                    "seed":seed, "label":label,
                    "status":f"unavailable: {type(e).__name__}",
                    "semantic_normalization":sem,
                    "segmentation":seg, "miner":miner,
                })
    return pd.DataFrame(rows)
