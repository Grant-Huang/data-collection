from typing import Dict
import pandas as pd
from .catalog import TOOL_VARIANTS

TOOL_TO_CAPABILITY: Dict[str,str] = {}
for capability, tools in TOOL_VARIANTS.items():
    for tool in tools:
        TOOL_TO_CAPABILITY[tool] = capability

def normalize_events(df: pd.DataFrame, use_semantics: bool = True) -> pd.DataFrame:
    out = df.copy()
    if use_semantics:
        out["activity"] = out.apply(
            lambda r: TOOL_TO_CAPABILITY.get(r["tool_name"], r["capability"]),
            axis=1
        )
    else:
        out["activity"] = out["tool_name"]
    return out
