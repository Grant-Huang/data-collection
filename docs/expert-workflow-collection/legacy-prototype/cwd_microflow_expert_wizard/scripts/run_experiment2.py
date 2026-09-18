from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cwd.experiment import experiment2_matrix

outdir = ROOT / "outputs"
outdir.mkdir(exist_ok=True)
df = experiment2_matrix()
df.to_csv(outdir / "experiment2_results.csv", index=False)

summary = df.groupby("segmentation_method").agg(
    boundary_precision=("boundary_precision","mean"),
    boundary_recall=("boundary_recall","mean"),
    boundary_f1=("boundary_f1","mean"),
    microflow_f1=("f1","mean"),
    avg_nodes=("avg_nodes","mean"),
    avg_edges=("avg_edges","mean"),
).sort_values("microflow_f1", ascending=False)

print(summary.to_string())
summary.to_csv(outdir / "experiment2_summary.csv")
