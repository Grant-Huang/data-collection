from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cwd.experiment import paper_baseline_matrix

df=paper_baseline_matrix(n_cases=500,seeds=(11,22,33,44,55))
out=ROOT/"outputs"
out.mkdir(exist_ok=True)
df.to_csv(out/"paper_baselines.csv",index=False)
ok=df[df["status"]=="ok"]
if not ok.empty:
    summary=ok.groupby("label").agg(
        f1_mean=("f1","mean"),
        f1_std=("f1","std"),
        boundary_f1_mean=("boundary_f1","mean"),
        avg_nodes=("avg_nodes","mean"),
        avg_edges=("avg_edges","mean"),
    ).sort_values("f1_mean",ascending=False)
    print(summary.to_string())
    summary.to_csv(out/"paper_baselines_summary.csv")
unavailable=df[df["status"]!="ok"][["label","status"]].drop_duplicates()
if not unavailable.empty:
    print("\nUnavailable baselines:")
    print(unavailable.to_string(index=False))
