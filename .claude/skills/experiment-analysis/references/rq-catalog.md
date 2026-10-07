# RQ → metric/function map

Source of truth for the RQ wording is
`docs/expert-workflow-collection/legacy-prototype/TWO_STAGE_PAPER_STRUCTURE_DAG.md`
("Paper 1 研究问题（更新版）" and "Paper 2 研究问题"). If that file changes, this
table can drift — skim the relevant RQ section there before relying on the
wording quoted below for a report.

All functions below live under
`docs/expert-workflow-collection/legacy-prototype/cwd_microflow_expert_wizard/cwd/`.
Paths are relative to that `cwd_microflow_expert_wizard/` directory unless
otherwise noted.

## Paper 1

| RQ | Question (quote in reports) | Primary function(s) | Key metric columns |
|---|---|---|---|
| RQ1 | Work Graph Recoverability — 能否从人—Agent制造协作轨迹中恢复稳定的工作依赖结构，而不是仅依赖时间顺序？ | `experiment.paper_baseline_matrix`, `evaluation.graph_similarity` (via `match_workflows`) | `edge_f1`, `fork_f1`, `join_f1`, `branch_type_accuracy` |
| RQ2 | Work-Unit Partitioning — dependency-aware / semantic graph partition 是否优于纯 change-point segmentation？ | `experiment.paper_baseline_matrix` (compare `segmentation` in {heuristic, embedding_cp, graph_semantic, oracle}), `evaluation.segmentation_metrics`, `evaluation.episode_membership_metrics`, `evaluation.tolerant_boundary_metrics` | `boundary_f1`, `episode_ari`, `episode_nmi`, `episode_pairwise_f1`, `tolerant_boundary_f1@1`, `tolerant_boundary_f1@2` |
| RQ3 | Reusable Subgraph Discovery — 是否可以从不同执行变体中发现稳定的 reusable operational subgraphs？ | `experiment.paper_baseline_matrix`, `evaluation.match_workflows`, `evaluation.microflow_classification_metrics` | `node_f1`, `edge_f1`, `fork_f1`, `join_f1`, `structural_similarity`, classification `f1` |
| RQ4 | Robustness — 在 business variation / execution deviation / logging imperfection 等扰动下是否仍能恢复？ | `advanced_experiments.disturbance_ablation`, `advanced_experiments.robustness_curve` | `f1`, `boundary_f1`, `marginal_f1_drop`, curve of a metric vs. `level` for one `factor` |
| RQ5 | Reusability / Generalization — 发现的子图是否跨 Case/Scenario/Tool/Actor 重复，能否解释 unseen workflow compositions？ | `advanced_experiments.reusability_generalization` | `heldout_event_reuse_coverage`, `heldout_microflow_composition_coverage`, `case_support`, `scenario_breadth`, `reuse_diversity` |
| RQ6 | Prospective Utility（轻量）— 检索到的 reusable operational subgraph 是否能作为未来任务的 procedural guidance？ | `advanced_experiments.retrieval_utility_simulation` | `task_success_rate`, `avg_steps`, `avg_tool_calls`, `avg_human_interventions` (compare `without_microflow` vs `with_retrieved_microflow`) |

Note the doc's own framing for RQ2: "Exact Boundary Accuracy is insufficient
for graph-structured collaborative work" — a report touching RQ2 should
present the ARI/NMI/pairwise-F1 family alongside boundary F1, not boundary F1
alone, or it's silently reintroducing the exact-boundary assumption the paper
argues against.

## Paper 2

Paper 2's RQs (Skill Compilation, Hierarchical Composition, Parallel
Composition, Execution-Guided Evolution, Negative Transfer/Governance,
Organizational Knowledge Retention) describe experiments that **do not have
corresponding functions in `cwd/` yet** — that module only covers Paper 1's
discovery pipeline. If a request maps to a Paper 2 RQ, say so plainly and
stop rather than trying to approximate it from Paper 1 data; do not stretch
`retrieval_utility_simulation` (a Paper 1, RQ6 "lightweight" simulation) into
evidence for Paper 2's execution/composition/evolution claims, and don't
fabricate a script for machinery that isn't built.

## Which function to run vs. which CSV to read

`experiment.paper_baseline_matrix(seeds=(11,22,33,44,55))` is the single
richest source — one call produces every RQ1–RQ3 metric across 11 conditions
× 5 seeds in one DataFrame. Prefer it over `experiment1_matrix` /
`experiment2_matrix` (older, narrower, module-organized rather than
RQ-organized) unless the user specifically asks to reproduce the exact
`outputs/experiment1_summary.csv` / `experiment2_summary.csv` tables.

If `outputs/paper_baselines.csv` already exists and its mtime is newer than
`cwd/experiment.py`, `cwd/evaluation.py`, and `cwd/generator.py`, read it
instead of re-running (a full run takes real time — 11 conditions × 5 seeds).
Otherwise re-run and overwrite it.
