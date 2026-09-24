"""Reusable stats + chart + report-section helpers for the experiment-analysis
skill. Every invocation of the skill needs the same handful of operations
(aggregate across seeds, test whether a difference is real, plot it, write a
markdown section) -- they're written once here instead of being reinvented
(slightly differently, with slightly different bugs) on every run.

Usable as a library (`from analyze import summarize, paired_test, ...`) or
from the command line for the common case of "summarize this CSV's metric
columns grouped by some label column":

    python analyze.py summarize outputs/paper_baselines.csv \\
        --group-col label --metric-cols edge_f1 fork_f1 join_f1 \\
        --out outputs/report/figures/rq1_edge_fork_join.png

Requires: pandas, numpy, scipy, matplotlib (already in requirements.txt --
no new dependency).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
from scipy import stats


def summarize(df: pd.DataFrame, group_col: str, metric_cols: Sequence[str]) -> pd.DataFrame:
    """Mean, std, 95% CI half-width, and n per group for each metric.

    The CI is a normal approximation (mean +/- 1.96 * sem) -- fine for the
    seed counts this pipeline actually uses (5-10). Don't report a bare mean
    difference as a finding; report mean +/- CI so a reader can see whether
    the groups' intervals overlap.
    """
    rows = []
    for group_val, g in df.groupby(group_col, sort=False):
        row = {group_col: group_val, "n": len(g)}
        for col in metric_cols:
            vals = g[col].dropna().to_numpy(dtype=float)
            if len(vals) == 0:
                row[f"{col}_mean"] = np.nan
                row[f"{col}_std"] = np.nan
                row[f"{col}_ci95"] = np.nan
                continue
            mean = float(np.mean(vals))
            std = float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0
            sem = std / np.sqrt(len(vals)) if len(vals) > 1 else 0.0
            ci95 = float(1.96 * sem)
            row[f"{col}_mean"] = mean
            row[f"{col}_std"] = std
            row[f"{col}_ci95"] = ci95
        rows.append(row)
    return pd.DataFrame(rows)


def to_markdown_table(df: pd.DataFrame, float_fmt: str = "{:.3f}") -> str:
    """Plain markdown table, no `tabulate` dependency (pandas.to_markdown
    needs it and it's not in requirements.txt -- don't add a dependency for
    a table formatter). Good enough for a report; not meant for huge frames.
    """
    def fmt(v: object) -> str:
        if isinstance(v, float):
            return "nan" if pd.isna(v) else float_fmt.format(v)
        return str(v)

    cols = list(df.columns)
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    body = "\n".join("| " + " | ".join(fmt(v) for v in row) + " |" for row in df.itertuples(index=False))
    return "\n".join([header, sep, body])


def paired_test(
    df: pd.DataFrame,
    group_col: str,
    value_col: str,
    condition_a: str,
    condition_b: str,
    id_col: str = "seed",
) -> dict:
    """Is condition_a actually different from condition_b, or is the mean gap
    just seed noise? Matches rows by `id_col` (normally the seed) so the test
    is paired -- each seed's A result is compared to that *same* seed's B
    result, which is a much stronger test than comparing the two groups'
    means in isolation.

    Uses the Wilcoxon signed-rank test (no normality assumption, robust with
    few seeds) and falls back to a paired t-test if Wilcoxon can't run (e.g.
    all differences are zero, or fewer than ~2 pairs).

    Returns {"n_pairs", "mean_diff", "test", "statistic", "p_value"}. A
    result with n_pairs < 3 is not a claim -- say so in the report rather
    than quoting a p-value that isn't meaningful with two seeds.
    """
    a = df[df[group_col] == condition_a].set_index(id_col)[value_col]
    b = df[df[group_col] == condition_b].set_index(id_col)[value_col]
    paired = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    n = len(paired)
    if n == 0:
        return {"n_pairs": 0, "mean_diff": np.nan, "test": None, "statistic": np.nan, "p_value": np.nan}

    diff = paired["a"] - paired["b"]
    mean_diff = float(diff.mean())
    if n < 3 or (diff == 0).all():
        return {"n_pairs": n, "mean_diff": mean_diff, "test": "insufficient_pairs", "statistic": np.nan, "p_value": np.nan}

    try:
        statistic, p_value = stats.wilcoxon(paired["a"], paired["b"])
        test_name = "wilcoxon"
    except ValueError:
        statistic, p_value = stats.ttest_rel(paired["a"], paired["b"])
        test_name = "paired_t"
    return {"n_pairs": n, "mean_diff": mean_diff, "test": test_name, "statistic": float(statistic), "p_value": float(p_value)}


def bar_with_ci(
    summary_df: pd.DataFrame,
    group_col: str,
    metric_col: str,
    out_path: str | Path,
    title: str | None = None,
    ylabel: str | None = None,
) -> Path:
    """Bar chart with 95% CI error bars from a `summarize()` output.
    `metric_col` is the bare metric name (e.g. "edge_f1"), not the
    "_mean"-suffixed column -- this reads {metric_col}_mean/_ci95 itself.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = summary_df[group_col].astype(str).tolist()
    means = summary_df[f"{metric_col}_mean"].to_numpy()
    cis = summary_df[f"{metric_col}_ci95"].to_numpy()

    fig, ax = plt.subplots(figsize=(max(6, 0.6 * len(labels)), 4.5))
    x = np.arange(len(labels))
    ax.bar(x, means, yerr=cis, capsize=4, color="#4C72B0")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_ylabel(ylabel or metric_col)
    ax.set_title(title or f"{metric_col} by {group_col} (mean +/- 95% CI)")
    ax.set_ylim(bottom=0)
    fig.tight_layout()

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def line_with_ci(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    out_path: str | Path,
    group_col: str | None = None,
    title: str | None = None,
    ylabel: str | None = None,
) -> Path:
    """Line chart for a metric against a swept factor (robustness curves:
    metric value vs. disturbance level). If `group_col` is given, draws one
    line per group (e.g. one line per segmentation method) so curves can be
    compared directly instead of across separate figures.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    if group_col:
        for group_val, g in df.groupby(group_col, sort=False):
            g = g.sort_values(x_col)
            agg = g.groupby(x_col)[y_col].agg(["mean", "std", "count"]).reset_index()
            ci = 1.96 * agg["std"].fillna(0) / agg["count"].clip(lower=1).pow(0.5)
            ax.errorbar(agg[x_col], agg["mean"], yerr=ci, marker="o", capsize=3, label=str(group_val))
        ax.legend()
    else:
        g = df.sort_values(x_col)
        agg = g.groupby(x_col)[y_col].agg(["mean", "std", "count"]).reset_index()
        ci = 1.96 * agg["std"].fillna(0) / agg["count"].clip(lower=1).pow(0.5)
        ax.errorbar(agg[x_col], agg["mean"], yerr=ci, marker="o", capsize=3, color="#4C72B0")

    ax.set_xlabel(x_col)
    ax.set_ylabel(ylabel or y_col)
    ax.set_title(title or f"{y_col} vs {x_col}")
    fig.tight_layout()

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def append_report_section(
    report_path: str | Path,
    rq_id: str,
    rq_question: str,
    table_md: str,
    figure_paths: Sequence[str | Path],
    interpretation: str,
    caveat: str | None = None,
) -> Path:
    """Append one RQ's section to the running report, creating the file with
    a title if it doesn't exist yet. Figures are referenced with paths
    relative to the report file's own directory so the report stays portable
    if the whole report/ folder is moved.

    `caveat`, when given, is rendered as a distinct "> Evidence boundary:"
    blockquote -- keep this populated whenever the finding touches anything
    PAPER_READINESS.md's "not yet fully supported" list covers. An
    interpretation with no caveat should mean the claim is genuinely inside
    the "strongly supported" boundary, not that nobody checked.
    """
    report_path = Path(report_path)
    report_dir = report_path.parent
    report_dir.mkdir(parents=True, exist_ok=True)

    if not report_path.exists():
        report_path.write_text(
            "# Experiment Report\n\n"
            "Auto-assembled by the experiment-analysis skill. Sections are organized "
            "by research question, per TWO_STAGE_PAPER_STRUCTURE_DAG.md's own instruction "
            "not to organize Results by algorithm/module. Re-running an RQ replaces its "
            "section; it does not duplicate it.\n\n"
        )

    existing = report_path.read_text()
    heading = f"## {rq_id}: {rq_question}"

    section_lines = [heading, "", table_md.strip(), ""]
    for fig in figure_paths:
        fig = Path(fig)
        # os.path.relpath (not Path.relative_to) handles both relative and
        # absolute inputs and doesn't require fig to be inside report_dir's
        # subtree -- resolve both to absolute first so "outputs/report/x.png"
        # passed in from a different CWD still comes out relative to the
        # report file's own directory, not wherever the caller happened to be.
        rel = os.path.relpath(fig.resolve(), report_dir.resolve())
        section_lines.append(f"![{fig.stem}]({rel})")
    section_lines.append("")
    section_lines.append(interpretation.strip())
    if caveat:
        section_lines.append("")
        section_lines.append(f"> Evidence boundary: {caveat.strip()}")
    section_lines.append("")
    new_section = "\n".join(section_lines)

    # Replace an existing section with the same heading (re-running an RQ
    # updates it in place) instead of appending a duplicate.
    marker = f"\n{heading}\n"
    if marker in ("\n" + existing):
        head, _, rest = existing.partition(marker)
        # find the next "## " heading to know where this section ends
        next_idx = rest.find("\n## ")
        rest_after = rest[next_idx:] if next_idx != -1 else ""
        updated = head + "\n" + new_section + "\n" + rest_after.lstrip("\n")
        report_path.write_text(updated)
    else:
        with report_path.open("a") as f:
            f.write("\n" + new_section + "\n")

    return report_path


def _cli_summarize(args: argparse.Namespace) -> None:
    df = pd.read_csv(args.csv)
    summary = summarize(df, args.group_col, args.metric_cols)
    print(summary.to_string(index=False))
    if args.out:
        bar_with_ci(summary, args.group_col, args.metric_cols[0], args.out)
        print(f"\nchart written to {args.out}", file=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("summarize", help="mean/std/95%% CI per group, optionally chart the first metric")
    s.add_argument("csv")
    s.add_argument("--group-col", required=True)
    s.add_argument("--metric-cols", nargs="+", required=True)
    s.add_argument("--out", help="PNG path; if given, charts the first metric column")
    s.set_defaults(func=_cli_summarize)

    return p


if __name__ == "__main__":
    parser = _build_parser()
    ns = parser.parse_args()
    ns.func(ns)
