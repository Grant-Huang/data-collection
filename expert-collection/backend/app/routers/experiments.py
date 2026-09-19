"""Experiment Center endpoints -- PRD 14, Phase 4 sub-scope (IMPLEMENTATION_PLAN.md section
7): create/list/detail/compare work for every method; only `consensus_dfg` actually executes.
Runs go through a real async transition (queued -> running -> completed/failed) via FastAPI
BackgroundTasks, not a fake progress bar.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException

from .. import audit, db, experiments as engine, explain
from ..models import (
    ComparisonRequest,
    ComparisonResult,
    CreateExperimentRequest,
    ExperimentDetail,
    ExperimentSummary,
    ExplanationUpdateRequest,
)

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_summary(exp: dict) -> ExperimentSummary:
    metrics = exp.get("metrics") or {}
    return ExperimentSummary(
        id=exp["id"], name=exp["name"], dataset_version_id=exp["dataset_version_id"],
        dataset_label=exp["dataset_label"], method=exp["method"], model_name=exp.get("model_name"),
        status=exp["status"], created_by=exp["created_by"], created_at=exp["created_at"],
        node_f1=metrics.get("node_f1"), graph_structural_f1=metrics.get("graph_structural_f1"),
    )


def _to_detail(exp: dict) -> ExperimentDetail:
    return ExperimentDetail(**{**exp, **_to_summary(exp).model_dump()})


def _run_experiment(exp_id: str) -> None:
    exp = db.get_experiment(exp_id)
    if not exp:
        return
    exp["status"] = "running"
    db.save_experiment(exp)

    try:
        if exp["method"] not in engine.IMPLEMENTED_METHODS:
            raise RuntimeError(f"方法 {exp['method']} 本轮未接入真实执行引擎，无法产出结果")

        version = db.get_dataset_version(exp["dataset_version_id"])
        if not version:
            raise RuntimeError("引用的数据集版本不存在")

        train_ids, test_ids = engine.split_train_test(version["workflow_ids"], exp["seed"], exp["train_split"])
        train_records = [db.get(wid) for wid in train_ids]
        test_records = [db.get(wid) for wid in test_ids]
        train_graphs = [r["graph"] for r in train_records if r]
        test_records = [r for r in test_records if r]
        test_graphs = [r["graph"] for r in test_records]
        test_names = [r["name"] for r in test_records]

        result = engine.run_consensus_dfg(train_graphs, test_graphs, test_names)
        explanation = explain.explain_experiment(
            result["metrics"], result["error_analysis"], len(train_graphs), len(test_graphs)
        )

        exp.update({
            "status": "completed",
            "train_count": len(train_graphs),
            "test_count": len(test_graphs),
            "metrics": result["metrics"],
            "consensus_graph": result["consensus_graph"],
            "error_analysis": result["error_analysis"],
            "explanation": explanation,
            "explanation_edited": False,
        })
    except Exception as e:  # noqa: BLE001 -- surfaced to the user as failure_reason, not swallowed
        exp["status"] = "failed"
        exp["failure_reason"] = str(e)

    db.save_experiment(exp)


@router.post("", response_model=ExperimentDetail)
def create_experiment(req: CreateExperimentRequest, background_tasks: BackgroundTasks) -> ExperimentDetail:
    version = db.get_dataset_version(req.dataset_version_id)
    if not version:
        raise HTTPException(status_code=404, detail="dataset version not found")

    exp_id = uuid.uuid4().hex[:12]
    exp = {
        "id": exp_id,
        "name": req.name,
        "source_type": req.source_type,
        "dataset_version_id": req.dataset_version_id,
        "dataset_label": f"{version['name']} v{version['version_number']}",
        "input_version": req.input_version,
        "representation": req.representation,
        "method": req.method,
        "model_name": req.model_name if req.method == "llm_extractor" else None,
        "prompt_version": req.prompt_version,
        "temperature": req.temperature,
        "seed": req.seed,
        "train_split": req.train_split,
        "status": "queued",
        "created_by": req.actor_role or "unknown",
        "created_at": _now(),
        "train_count": None, "test_count": None, "metrics": {},
        "explanation": None, "explanation_edited": False,
        "consensus_graph": None, "error_analysis": [], "failure_reason": None,
    }
    db.save_experiment(exp)
    audit.log(exp["created_by"], "experiment_create", {"experiment_id": exp_id, "method": req.method})
    background_tasks.add_task(_run_experiment, exp_id)
    return _to_detail(exp)


@router.get("", response_model=list[ExperimentSummary])
def list_experiments() -> list[ExperimentSummary]:
    return [_to_summary(e) for e in db.list_experiments()]


@router.get("/{exp_id}", response_model=ExperimentDetail)
def get_experiment(exp_id: str) -> ExperimentDetail:
    exp = db.get_experiment(exp_id)
    if not exp:
        raise HTTPException(status_code=404, detail="experiment not found")
    return _to_detail(exp)


@router.put("/{exp_id}/explanation", response_model=ExperimentDetail)
def update_explanation(exp_id: str, req: ExplanationUpdateRequest) -> ExperimentDetail:
    exp = db.get_experiment(exp_id)
    if not exp:
        raise HTTPException(status_code=404, detail="experiment not found")
    exp["explanation"] = req.text
    exp["explanation_edited"] = True
    db.save_experiment(exp)
    return _to_detail(exp)


@router.post("/{exp_id}/regenerate-explanation", response_model=ExperimentDetail)
def regenerate_explanation(exp_id: str) -> ExperimentDetail:
    exp = db.get_experiment(exp_id)
    if not exp:
        raise HTTPException(status_code=404, detail="experiment not found")
    if exp["status"] != "completed":
        raise HTTPException(status_code=400, detail="只有已完成的实验才能重新生成解读")
    exp["explanation"] = explain.explain_experiment(
        exp["metrics"], exp["error_analysis"], exp["train_count"], exp["test_count"]
    )
    exp["explanation_edited"] = False
    db.save_experiment(exp)
    return _to_detail(exp)


@router.post("/compare", response_model=ComparisonResult)
def compare_experiments(req: ComparisonRequest) -> ComparisonResult:
    if not (2 <= len(req.experiment_ids) <= 5):
        raise HTTPException(status_code=400, detail="请选择 2～5 个已完成的实验进行对比")

    exps = [db.get_experiment(eid) for eid in req.experiment_ids]
    if any(e is None for e in exps):
        raise HTTPException(status_code=404, detail="部分实验不存在")
    if any(e["status"] != "completed" for e in exps):
        raise HTTPException(status_code=400, detail="只能对比已完成的实验")

    metric_keys = [
        ("node_f1", "Node F1", "higher"), ("edge_f1", "Edge F1", "higher"),
        ("graph_structural_f1", "Graph Structural F1", "higher"),
        ("structural_match_rate", "结构特征匹配率", "higher"),
    ]
    metric_table: dict = {"rows": []}
    for key, label, direction in metric_keys:
        values = [e["metrics"].get(key) for e in exps]
        valid = [v for v in values if v is not None]
        best = (max(valid) if direction == "higher" else min(valid)) if valid else None
        metric_table["rows"].append({
            "key": key, "label": label, "direction": direction,
            "values": values, "best_value": best,
        })

    narrative = explain.explain_comparison([{"name": e["name"], "metrics": e["metrics"]} for e in exps])

    return ComparisonResult(experiments=[_to_summary(e) for e in exps], metric_table=metric_table, narrative=narrative)
