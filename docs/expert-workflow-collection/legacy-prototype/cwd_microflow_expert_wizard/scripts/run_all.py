from pathlib import Path
import subprocess, sys

ROOT = Path(__file__).resolve().parents[1]
for script in ["run_experiment1.py","run_experiment2.py"]:
    print("\\n===", script, "===")
    subprocess.run([sys.executable, str(ROOT / "scripts" / script)], check=True)
print("\\nResults written to", ROOT / "outputs")
