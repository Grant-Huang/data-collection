from typing import List, Tuple, Optional
import numpy as np
import pandas as pd
from .catalog import CAPABILITY_FAMILY

def oracle_segmentation(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["episode_pred"] = out["episode_id_gt"]
    return out

def no_segmentation(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["episode_pred"] = out["case_id"]
    return out

def heuristic_segmentation(df: pd.DataFrame, min_events: int = 2) -> pd.DataFrame:
    out_parts = []
    for case_id, g in df.sort_values(["case_id","timestamp"]).groupby("case_id", sort=False):
        g = g.copy()
        seg, last_family, last_intent, count = 0, None, None, 0
        preds = []
        for _, r in g.iterrows():
            activity = r.get("activity", r.get("capability",""))
            fam = CAPABILITY_FAMILY.get(activity, "noise")
            intent = r.get("intent","")
            action_type = r.get("action_type","work")
            boundary = False
            if count >= min_events:
                if action_type == "trigger":
                    boundary = True
                elif last_family not in (None,"noise") and fam not in ("noise",last_family):
                    boundary = True
                elif last_intent and intent and intent != last_intent and fam != "noise":
                    boundary = _intent_group(intent) != _intent_group(last_intent)
            if boundary:
                seg += 1
                count = 0
            preds.append(f"{case_id}_H{seg:02d}")
            if fam != "noise":
                last_family = fam
            if intent not in ("", "supporting_activity", "incidental_activity"):
                last_intent = intent
            count += 1
        g["episode_pred"] = preds
        out_parts.append(g)
    return pd.concat(out_parts, ignore_index=True)

def embedding_change_point_segmentation(
    df: pd.DataFrame,
    model_name: str = "all-MiniLM-L6-v2",
    window: int = 2,
    threshold_quantile: float = 0.70,
    min_segment_events: int = 2,
    backend: str = "auto",
    random_state: int = 42,
) -> pd.DataFrame:
    """
    Unsupervised semantic change-point segmentation.

    Event representations use capability/activity + intent + actor role + object type.
    Preferred backend: sentence-transformers.
    Reproducible fallback: TF-IDF -> TruncatedSVD dense embeddings.

    A boundary score at position i is cosine distance between the mean embedding
    of the left and right windows. Local maxima above a within-case quantile are
    retained subject to a minimum segment length.
    """
    out_parts = []
    for case_id, g in df.sort_values(["case_id","timestamp"]).groupby("case_id", sort=False):
        g = g.copy().reset_index(drop=True)
        texts = [_event_text(r) for _, r in g.iterrows()]
        X, used_backend = _embed(texts, model_name, backend, random_state)
        scores = _change_scores(X, window)
        boundaries = _select_boundaries(
            scores, threshold_quantile=threshold_quantile,
            min_segment_events=min_segment_events
        )
        seg = 0
        preds = []
        for i in range(len(g)):
            if i in boundaries and i > 0:
                seg += 1
            preds.append(f"{case_id}_ECP{seg:02d}")
        g["episode_pred"] = preds
        g["embedding_cp_score"] = scores
        g["embedding_backend"] = used_backend
        out_parts.append(g)
    return pd.concat(out_parts, ignore_index=True)

def _event_text(r) -> str:
    activity = str(r.get("activity", r.get("capability","")))
    return (
        f"activity {activity}; intent {r.get('intent','')}; "
        f"actor {r.get('actor_type','')} {r.get('actor_role','')}; "
        f"object {r.get('object_type','')}; status {r.get('status','')}"
    )

def _embed(texts, model_name, backend, random_state):
    if backend in ("auto", "sentence_transformer"):
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(model_name)
            X = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            return np.asarray(X, dtype=float), "sentence_transformer"
        except Exception:
            if backend == "sentence_transformer":
                raise
    # deterministic dense semantic fallback, also useful as an ablation baseline
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import TruncatedSVD
    from sklearn.preprocessing import normalize
    vec = TfidfVectorizer(ngram_range=(1,2), token_pattern=r"(?u)\b[\w_.-]+\b")
    Xs = vec.fit_transform(texts)
    if len(texts) <= 2 or Xs.shape[1] <= 2:
        return normalize(Xs).toarray(), "tfidf"
    k = max(2, min(32, Xs.shape[0]-1, Xs.shape[1]-1))
    svd = TruncatedSVD(n_components=k, random_state=random_state)
    X = normalize(svd.fit_transform(Xs))
    return np.asarray(X, dtype=float), "tfidf_svd"

def _cosine_distance(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(1.0 - np.dot(a,b)/(na*nb))

def _change_scores(X, window):
    n = len(X)
    scores = np.zeros(n, dtype=float)
    for i in range(1, n):
        l0 = max(0, i-window)
        r1 = min(n, i+window)
        left = X[l0:i]
        right = X[i:r1]
        if len(left) and len(right):
            scores[i] = _cosine_distance(left.mean(axis=0), right.mean(axis=0))
    return scores

def _select_boundaries(scores, threshold_quantile=0.70, min_segment_events=2):
    if len(scores) <= 2:
        return set()
    positives = scores[1:]
    threshold = float(np.quantile(positives, threshold_quantile))
    candidates = []
    for i in range(1, len(scores)):
        left = scores[i-1] if i-1 >= 0 else -1
        right = scores[i+1] if i+1 < len(scores) else -1
        if scores[i] >= threshold and scores[i] >= left and scores[i] >= right:
            candidates.append(i)
    # greedy by score, enforce minimum distance between boundaries
    accepted = []
    for i in sorted(candidates, key=lambda x: scores[x], reverse=True):
        if i < min_segment_events or len(scores)-i < 1:
            continue
        if all(abs(i-j) >= min_segment_events for j in accepted):
            accepted.append(i)
    return set(sorted(accepted))

def _intent_group(intent: str) -> str:
    if not intent:
        return ""
    for key in [
        "context","cause","quality","production_impact","delivery",
        "recovery","approval","verify","close"
    ]:
        if key in intent:
            return key
    return intent.split("_")[0]

def boundary_labels(df: pd.DataFrame, episode_col: str) -> List[int]:
    labels = []
    for _, g in df.sort_values(["case_id","timestamp"]).groupby("case_id", sort=False):
        prev = None
        for i, (_, r) in enumerate(g.iterrows()):
            cur = r[episode_col]
            labels.append(1 if i == 0 or cur != prev else 0)
            prev = cur
    return labels

def dependency_semantic_segmentation(df: pd.DataFrame) -> pd.DataFrame:
    """Graph-aware episode partitioning baseline.

    Unlike change-point segmentation, this method does not assume that an episode is a
    contiguous time interval. It uses observable work-dependency links and semantic
    capability families. Cross-family dependency edges are cut; connected components
    in the remaining dependency graph become predicted episodes.
    """
    import networkx as nx
    from .graph_utils import parse_ids
    out_parts=[]
    for case_id,g in df.sort_values(["case_id","timestamp"]).groupby("case_id",sort=False):
        g=g.copy()
        id2row={str(r["event_id"]):r for _,r in g.iterrows()}
        graph=nx.Graph(); graph.add_nodes_from(id2row)
        for eid,r in id2row.items():
            act=str(r.get("activity",r.get("capability","")))
            fam=CAPABILITY_FAMILY.get(act,_intent_group(str(r.get("intent",""))) or "unknown")
            for pid in parse_ids(r.get("predecessor_event_ids","")):
                if pid not in id2row: continue
                pr=id2row[pid]
                pact=str(pr.get("activity",pr.get("capability","")))
                pfam=CAPABILITY_FAMILY.get(pact,_intent_group(str(pr.get("intent",""))) or "unknown")
                # Keep dependency edges within a semantic work family. Noise/supporting
                # actions inherit local connectivity instead of forcing a split.
                if fam==pfam or fam in {"noise","unknown"} or pfam in {"noise","unknown"}:
                    graph.add_edge(pid,eid)
        # Isolated events are attached to nearest dependency-neighbor family where possible.
        comps=list(nx.connected_components(graph))
        comp_of={eid:i for i,c in enumerate(comps) for eid in c}
        preds=[]
        for _,r in g.iterrows():
            preds.append(f"{case_id}_DG{comp_of[str(r['event_id'])]:02d}")
        g["episode_pred"]=preds
        g["graph_segmentation"]=True
        out_parts.append(g)
    return pd.concat(out_parts,ignore_index=True) if out_parts else df.copy()
