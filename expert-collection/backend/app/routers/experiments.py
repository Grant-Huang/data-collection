"""Experiment Center endpoints -- PRD 14, Phase 4 sub-scope (IMPLEMENTATION_PLAN.md section
7 / §14): create/list/detail/compare work for every method; `consensus_dfg`, `pm4py_inductive`
and `pm4py_heuristics` actually execute (see experiments.py), `llm_extractor` does not yet
(needs its own input/output protocol design, not just a metrics swap).
Runs go through a real async transition (queued -> running -> completed/failed) via FastAPI
BackgroundTasks, not a fake progress bar.

Multi-dataset / Combined Train (PRD §14.1): `CreateExperimentRequest.dataset_version_ids` is a
list, not a single id, and can span both source_types. Fixed two things at once doing this:
(1) the old code read every record via `db.get(workflow_id)`, which only has rows for
`expert_collected` -- a `public_extracted` version silently produced an empty train/test set
instead of an honest error; both now go through `dataset_records.records_for_export()`, which
already normalizes both source types. (2) Train pools across every selected version, but PRD
§14.1's hard rule ("允许 Combined Train，Test 仍必须分别报告，禁止只给一个混合总分") means the
train/test split happens per source_type *before* pooling, and every experiment carries both
an overall `metrics` and a per-source `metrics_by_source` -- never only a blended total.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException

from .. import audit, dataset_records, db, experiments as engine, explain
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
        id=exp["id"], name=exp["name"], dataset_version_ids=exp["dataset_version_ids"],
        dataset_label=exp["dataset_label"], source_types=exp["source_types"],
        method=exp["method"], model_name=exp.get("model_name"),
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

        versions = [db.get_dataset_version(vid) for vid in exp["dataset_version_ids"]]
        if any(v is None for v in versions):
            raise RuntimeError("引用的数据集版本不存在")

        # PRD §14.1's hard rule: Combined Train may pool records across every selected version
        # regardless of source_type, but Test must stay split out per source_type so results
        # can always be reported separately, never only a blended total -- so the split happens
        # per source_type BEFORE pooling into one train set, not after a single combined split.
        # `dataset_records.records_for_export` is what makes this loop source_type-agnostic in
        # the first place: before this, public_extracted records weren't reachable here at all
        # (see IMPLEMENTATION_PLAN.md's note on the old direct-`db.get(wid)` bug).
        seen_ids: set[str] = set()
        records_by_source: dict[str, list[dict]] = {}
        for version in versions:
            for r in dataset_records.records_for_export(version):
                rid = r.get("record_id")
                # Dataset versions are cumulative snapshots, so selecting two versions of the
                # same source (e.g. v1 and v2) can genuinely overlap -- count each record once.
                if not rid or rid in seen_ids:
                    continue
                seen_ids.add(rid)
                records_by_source.setdefault(version["source_type"], []).append(r)

        train_records: list[dict] = []
        test_records: list[dict] = []
        test_source_types: list[str] = []
        train_count_by_source: dict[str, int] = {}
        test_count_by_source: dict[str, int] = {}
        for source_type, records in records_by_source.items():
            record_ids = [r["record_id"] for r in records]
            train_ids, test_ids = engine.split_train_test(record_ids, exp["seed"], exp["train_split"])
            by_id = {r["record_id"]: r for r in records}
            train_count_by_source[source_type] = len(train_ids)
            test_count_by_source[source_type] = len(test_ids)
            for rid in train_ids:
                train_records.append(by_id[rid])
            for rid in test_ids:
                test_records.append(by_id[rid])
                test_source_types.append(source_type)

        train_graphs = [r["graph"] for r in train_records]
        test_graphs = [r["graph"] for r in test_records]
        test_names = [r.get("scenario", {}).get("scenario_name") or r["record_id"] for r in test_records]

        if exp["method"] == "consensus_dfg":
            result = engine.run_consensus_dfg(train_graphs, test_graphs, test_names, test_source_types)
        else:
            result = engine.run_pm4py_method(exp["method"], train_graphs, test_graphs, test_names, test_source_types)
        error_clusters = explain.cluster_error_cases(result["error_analysis"])
        explanation = explain.explain_experiment(
            result["metrics"], result["error_analysis"], len(train_graphs), len(test_graphs)
        )

        exp.update({
            "status": "completed",
            "train_count": len(train_graphs),
            "test_count": len(test_graphs),
            "train_count_by_source": train_count_by_source,
            "test_count_by_source": test_count_by_source,
            "metrics": result["metrics"],
            "metrics_by_source": result["metrics_by_source"],
            "consensus_graph": result["consensus_graph"],
            "error_analysis": result["error_analysis"],
            "error_clusters": error_clusters,
            "explanation": explanation,
            "explanation_edited": False,
        })
    except Exception as e:  # noqa: BLE001 -- surfaced to the user as failure_reason, not swallowed
        exp["status"] = "failed"
        exp["failure_reason"] = str(e)

    db.save_experiment(exp)


@router.post("", response_model=ExperimentDetail)
def create_experiment(req: CreateExperimentRequest, background_tasks: BackgroundTasks) -> ExperimentDetail:
    versions = [db.get_dataset_version(vid) for vid in req.dataset_version_ids]
    missing = [vid for vid, v in zip(req.dataset_version_ids, versions) if v is None]
    if missing:
        raise HTTPException(status_code=404, detail=f"数据集版本不存在：{', '.join(missing)}")

    exp_id = uuid.uuid4().hex[:12]
    exp = {
        "id": exp_id,
        "name": req.name,
        "dataset_version_ids": req.dataset_version_ids,
        "dataset_label": " + ".join(f"{v['name']} v{v['version_number']}" for v in versions),
        "source_types": sorted({v["source_type"] for v in versions}),
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
        "train_count": None, "test_count": None,
        "train_count_by_source": {}, "test_count_by_source": {},
        "metrics": {}, "metrics_by_source": {},
        "explanation": None, "explanation_edited": False,
        "consensus_graph": None, "error_analysis": [], "error_clusters": [], "failure_reason": None,
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
    exp["error_clusters"] = explain.cluster_error_cases(exp["error_analysis"])
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
