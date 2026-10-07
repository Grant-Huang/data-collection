---
name: experiment-analysis
description: >-
  Turn this repo's Collaborative Workflow Distillation experiment pipeline
  (docs/expert-workflow-collection/legacy-prototype/cwd_microflow_expert_wizard's
  paper_baseline_matrix / disturbance_ablation / robustness_curve /
  reusability_generalization / retrieval_utility_simulation, or their CSVs
  already sitting in that project's outputs/ folder) into an RQ-organized,
  chart-backed Markdown report for the paper being drafted in
  docs/expert-workflow-collection/legacy-prototype/TWO_STAGE_PAPER_STRUCTURE_DAG.md.
  Use this whenever the user asks to analyze or summarize experiment
  results, write or update a Results section for Paper 1 or Paper 2,
  produce charts/figures for a specific RQ, run an ablation or robustness
  sweep, or check whether a metric difference between two conditions is
  real or just seed noise -- even if phrased casually, e.g. "跑一下
  disturbance ablation 并出报告", "帮我看看 RQ2 的结果", "画个图看 embedding_cp
  是不是真的比 heuristic 好", or "这两组数据差异明显吗". Do NOT use this for the
  separate, much simpler experiment pipeline in
  expert-collection/backend/app/experiments.py (the live web app's
  Experiment Center) -- that's a different system with different metrics
  and no relation to this paper's evaluation code.
---

# Experiment analysis for the Collaborative Workflow Distillation paper

## Why this exists

`cwd_microflow_expert_wizard/cwd/` already computes every metric the paper's
RQs need (`evaluation.py`, `advanced_experiments.py`, `experiment.py`), and
`scripts/run_experiment1.py` etc. already run it -- but they stop at a
`groupby().mean()` printed to the console and a raw CSV. There's no chart,
no significance test (a 2% mean gap across 5 seeds could be signal or noise
-- nothing currently tells you which), and no report organized the way the
paper actually needs it. `TWO_STAGE_PAPER_STRUCTURE_DAG.md`'s own "6.
Results" section is explicit that results should be organized **by research
question, not by algorithm/module** -- this skill's whole job is closing
that specific gap: raw metrics in, an RQ-numbered report section with a
chart and an honestly-bounded claim out.

## Before anything else: read two files

1. **`references/rq-catalog.md`** (next to this file) -- maps each RQ to the
   function(s) that produce its metrics and the exact metric column names.
   Don't guess a function name or a column name; look it up here.
2. **`docs/expert-workflow-collection/legacy-prototype/cwd_microflow_expert_wizard/PAPER_READINESS.md`**
   -- the paper's own claim boundary: what's "strongly supported" by the
   current synthetic pipeline vs. "not yet fully supported" (real traces,
   expert-validated reusability, cross-org generalization, causal claims
   without repeated-seed testing, production value). Every interpretation
   you write has to sit on the correct side of that line. Re-read it each
   session rather than relying on memory -- it's short, and it's the one
   file in this skill you should never paraphrase from a stale mental copy.

## Workflow

**1. Identify which paper and RQ(s) the request maps to.** Use
`rq-catalog.md`. If it's a Paper 2 RQ, stop and say plainly that Paper 2's
skill-compilation/composition/evolution experiments have no corresponding
code yet in `cwd/` -- don't stretch a Paper 1 function (especially
`retrieval_utility_simulation`, which is explicitly a "lightweight" Paper 1
RQ6 simulation) into evidence for a Paper 2 claim.

**2. Get the data.** Prefer re-using a fresh CSV in
`cwd_microflow_expert_wizard/outputs/` over re-running (a full
`paper_baseline_matrix` run is 11 conditions x 5 seeds, not instant) --
check whether it's newer than `cwd/experiment.py`, `cwd/evaluation.py`, and
`cwd/generator.py`. Otherwise call the function from `rq-catalog.md`
directly (`cd` into `cwd_microflow_expert_wizard/` so the `cwd` package
imports, e.g. `python3 -c "from cwd.experiment import paper_baseline_matrix;
paper_baseline_matrix(seeds=(11,22,33,44,55)).to_csv('outputs/paper_baselines.csv', index=False)"`).
Always use multiple seeds (the functions default to 5) -- a single-seed run
can't support the statistics in step 3, and reporting it as if it could is
exactly the "causal claims without repeated-seed testing" gap
PAPER_READINESS.md flags as unsupported.

**3. Compute real statistics, not eyeballed means.** Use
`scripts/analyze.py`'s `summarize()` for mean/std/95% CI per condition, and
`paired_test()` whenever the report claims one condition beats another --
it pairs by seed (Wilcoxon signed-rank, falling back to a paired t-test) so
the comparison isn't confounded by which seeds happened to be easy or hard.
An `n_pairs < 3` result comes back as `test: "insufficient_pairs"` --
report that plainly instead of quoting a p-value that doesn't mean anything
yet.

**4. Chart it.** `bar_with_ci()` for cross-condition comparisons (RQ1-RQ3,
RQ5), `line_with_ci()` for a metric swept against a disturbance level
(RQ4's `robustness_curve` output, x=`level`, optionally one line per
`factor` value or per method via `group_col`). Save under
`cwd_microflow_expert_wizard/outputs/report/figures/`.

**5. Assemble the report section.** `append_report_section()` writes to
`cwd_microflow_expert_wizard/outputs/report/report.md`, keyed by RQ heading
-- re-running an RQ updates its section in place rather than duplicating
it, so repeated invocations converge on one running report instead of
scattering files. Always pass `caveat` when the finding touches anything on
PAPER_READINESS.md's "not yet fully supported" list; leave it unset only
when the claim is genuinely inside "strongly supported" (don't skip it out
of laziness -- an unset caveat is itself a claim that the finding is fully
supported).

**6. Write the interpretation like a reviewer would check it.** State what
was compared, what the numbers show, and stop -- do not extrapolate to "this
proves the method works in production" or similar. If `paired_test` came
back non-significant (or `insufficient_pairs`), say the difference isn't
established yet rather than describing the larger mean as if it won.

## Using `scripts/analyze.py`

Import it as a library from a Python one-liner or short script (it's not
meant to be copy-pasted -- call it):

```python
import sys; sys.path.insert(0, "<path-to-this-skill>/scripts")
from analyze import summarize, paired_test, bar_with_ci, line_with_ci, to_markdown_table, append_report_section

df = pd.read_csv(".../outputs/paper_baselines.csv")
rq2 = df[df["label"].isin(["Semantic + Rule Seg + Consensus DFG", "Semantic + Embedding CP + Consensus DFG"])]
summary = summarize(rq2, "label", ["boundary_f1", "episode_ari", "episode_nmi"])
test = paired_test(rq2, "label", "boundary_f1", "Semantic + Rule Seg + Consensus DFG", "Semantic + Embedding CP + Consensus DFG")
fig = bar_with_ci(summary, "label", "boundary_f1", ".../outputs/report/figures/rq2_boundary_f1.png")
append_report_section(
    ".../outputs/report/report.md", "RQ2",
    "Work-Unit Partitioning — dependency-aware / semantic graph partition 是否优于纯 change-point segmentation？",
    to_markdown_table(summary), [fig],
    f"Embedding change-point segmentation reaches boundary_f1={summary.iloc[1]['boundary_f1_mean']:.3f} "
    f"vs. {summary.iloc[0]['boundary_f1_mean']:.3f} for rule-based (paired {test['test']}, "
    f"p={test['p_value']:.3f}, n={test['n_pairs']} seeds).",
    caveat="Synthetic dataset only; not yet validated against real AgentNexus traces per PAPER_READINESS.md.",
)
```

It also has a `summarize` CLI subcommand for a quick look without writing
Python (`python3 analyze.py summarize outputs/paper_baselines.csv
--group-col label --metric-cols edge_f1 --out figures/edge_f1.png`), but the
library path is what you want for anything involving `paired_test` or a
report section.

## Scope reminder

This skill is specifically for the paper's evaluation pipeline under
`docs/expert-workflow-collection/legacy-prototype/cwd_microflow_expert_wizard/`.
The live web app has its own, unrelated experiment system
(`expert-collection/backend/app/experiments.py`, `node_f1`/`edge_f1`/
`graph_structural_f1`/`structural_match_rate` only, no charts, no report
export) -- if a request is actually about that (e.g. "the Experiment Center
page shows a failed run"), this skill doesn't apply.
