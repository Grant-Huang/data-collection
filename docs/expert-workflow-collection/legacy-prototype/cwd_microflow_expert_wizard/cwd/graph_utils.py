import json
from collections import defaultdict
from typing import Dict, Iterable, List, Set, Tuple
import pandas as pd


def parse_ids(value) -> List[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(x) for x in value if str(x)]
    s = str(value).strip()
    if not s:
        return []
    if s.startswith("["):
        try:
            return [str(x) for x in json.loads(s)]
        except Exception:
            pass
    return [x.strip() for x in s.replace(",", ";").split(";") if x.strip()]


def dump_ids(ids: Iterable[str]) -> str:
    return ";".join(str(x) for x in ids if str(x))


def edge_set_from_events(df: pd.DataFrame, pred_col: str = "predecessor_event_ids") -> Set[Tuple[str, str]]:
    if pred_col not in df.columns or "event_id" not in df.columns:
        return set()
    valid = set(df["event_id"].astype(str))
    edges = set()
    for _, r in df.iterrows():
        tgt = str(r["event_id"])
        for src in parse_ids(r.get(pred_col, "")):
            if src in valid:
                edges.add((src, tgt))
    return edges


def capability_edges_from_events(df: pd.DataFrame, pred_col: str = "predecessor_event_ids", activity_col: str = "activity"):
    if df.empty or activity_col not in df.columns:
        return set()
    id2act = {str(r["event_id"]): str(r[activity_col]) for _, r in df.iterrows()}
    out = set()
    for src, tgt in edge_set_from_events(df, pred_col):
        if src in id2act and tgt in id2act:
            out.add((id2act[src], id2act[tgt]))
    return out


def fork_join_signatures(nodes: Iterable[str], edges: Iterable[Tuple[str,str]]):
    outdeg, indeg = defaultdict(int), defaultdict(int)
    for a,b in edges:
        outdeg[a]+=1; indeg[b]+=1
    forks = {n for n in nodes if outdeg[n] > 1}
    joins = {n for n in nodes if indeg[n] > 1}
    return forks, joins


def control_type_map(df: pd.DataFrame):
    """Return node->branch_type for rows carrying observable/annotated control metadata."""
    out = {}
    if "activity" not in df.columns or "branch_type" not in df.columns:
        return out
    for _, r in df.iterrows():
        bt = str(r.get("branch_type", "") or "").strip().lower()
        if bt in {"and","xor","or"}:
            out[str(r["activity"])] = bt
    return out
