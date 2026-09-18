from pathlib import Path
import sys
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="Collaborative Workflow Distillation", layout="wide")

page = st.sidebar.radio(
    "页面 / Page",
    ["🧪 实验工作台", "🧭 专家数据采集 Wizard"],
    index=0,
)

if page == "🧭 专家数据采集 Wizard":
    from cwd.expert_wizard import render_expert_wizard
    render_expert_wizard()
else:
    import cwd.workbench_page  # renders the dynamic experiment workbench
