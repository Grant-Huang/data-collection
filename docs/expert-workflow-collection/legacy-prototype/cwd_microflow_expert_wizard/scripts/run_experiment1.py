from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cwd.experiment import experiment1_matrix

outdir = ROOT / "outputs"
outdir.mkdir(exist_ok=True)
df = experiment1_matrix()
df.to_csv(outdir / "experiment1_results.csv", index=False)

summary = df.groupby("method").agg(
    f1_mean=("f1","mean"),
    f1_std=("f1","std"),
    boundary_f1_mean=("boundary_f1","mean"),
    avg_nodes=("avg_nodes","mean"),
    avg_edges=("avg_edges","mean")
).sort_values("f1_mean", ascending=False)

print(summary.to_string())
summary.to_csv(outdir / "experiment1_summary.csv")
