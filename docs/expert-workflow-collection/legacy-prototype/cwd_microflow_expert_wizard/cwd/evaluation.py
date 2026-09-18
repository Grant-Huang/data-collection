from typing import Dict, List, Tuple
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from sklearn.metrics import precision_recall_fscore_support, adjusted_rand_score, normalized_mutual_info_score
from .catalog import MICROFLOWS
from .mining import DiscoveredWorkflow
from .segmentation import boundary_labels
from .graph_utils import fork_join_signatures


def gt_graph(mw_id: str):
    mw = MICROFLOWS[mw_id]
    nodes = {s.capability for s in mw.steps}
    edges = set(mw.graph_edges())
    branch_types = {}
    for cg in mw.control_groups:
        if cg.fork_from: branch_types[cg.fork_from] = cg.branch_type
        if cg.join_to: branch_types[cg.join_to] = cg.branch_type
    return nodes, edges, branch_types


def _set_prf(pred:set, gt:set):
    if not pred and not gt:
        return 1.0,1.0,1.0
    tp=len(pred & gt); p=tp/len(pred) if pred else 0.0; r=tp/len(gt) if gt else 0.0
    f=2*p*r/(p+r) if p+r else 0.0
    return p,r,f


def graph_similarity(discovered: DiscoveredWorkflow, mw_id: str) -> Dict[str,float]:
    gt_nodes, gt_edges, gt_branch_types = gt_graph(mw_id)
    pred_nodes, pred_edges = set(discovered.nodes), set(discovered.edges)
    node_p,node_r,node_f=_set_prf(pred_nodes,gt_nodes)
    edge_p,edge_r,edge_f=_set_prf(pred_edges,gt_edges)
    gt_forks,gt_joins=fork_join_signatures(gt_nodes,gt_edges)
    pr_forks,pr_joins=fork_join_signatures(pred_nodes,pred_edges)
    fork_p,fork_r,fork_f=_set_prf(pr_forks,gt_forks)
    join_p,join_r,join_f=_set_prf(pr_joins,gt_joins)
    comparable=set(gt_branch_types) & set(discovered.branch_types)
    branch_acc=(sum(discovered.branch_types[n]==gt_branch_types[n] for n in comparable)/len(comparable)) if comparable else np.nan
    structural=0.25*node_f+0.35*edge_f+0.20*fork_f+0.20*join_f
    return {
        "node_precision":node_p,"node_recall":node_r,"node_f1":node_f,
        "edge_precision":edge_p,"edge_recall":edge_r,"edge_f1":edge_f,
        "fork_precision":fork_p,"fork_recall":fork_r,"fork_f1":fork_f,
        "join_precision":join_p,"join_recall":join_r,"join_f1":join_f,
        "branch_type_accuracy":float(branch_acc) if not np.isnan(branch_acc) else np.nan,
        "structural_similarity":structural,
    }


def match_workflows(discovered: List[DiscoveredWorkflow]) -> Tuple[pd.DataFrame, Dict[int,str]]:
    gt_ids=list(MICROFLOWS)
    if not discovered: return pd.DataFrame(),{}
    score=np.zeros((len(discovered),len(gt_ids)))
    for i,w in enumerate(discovered):
        for j,mw in enumerate(gt_ids): score[i,j]=graph_similarity(w,mw)["structural_similarity"]
    rows,cols=linear_sum_assignment(-score); mapping={}; records=[]
    for i,j in zip(rows,cols):
        mapping[discovered[i].cluster_id]=gt_ids[j]
        records.append({"cluster_id":discovered[i].cluster_id,"matched_microflow":gt_ids[j],
                        "n_episodes":discovered[i].n_episodes,**graph_similarity(discovered[i],gt_ids[j])})
    return pd.DataFrame(records),mapping


def microflow_classification_metrics(clustered: pd.DataFrame, mapping: Dict[int,str]) -> Dict[str,float]:
    if not mapping or "microflow_gt" not in clustered:
        return {"precision":0.0,"recall":0.0,"f1":0.0}
    y_true=clustered["microflow_gt"].tolist(); y_pred=[mapping.get(int(c),"UNMATCHED") for c in clustered["cluster"]]
    p,r,f,_=precision_recall_fscore_support(y_true,y_pred,average="macro",zero_division=0)
    return {"precision":float(p),"recall":float(r),"f1":float(f)}


def segmentation_metrics(df: pd.DataFrame) -> Dict[str,float]:
    if "episode_id_gt" not in df.columns:
        return {"boundary_precision":np.nan,"boundary_recall":np.nan,"boundary_f1":np.nan}
    y_true=boundary_labels(df,"episode_id_gt"); y_pred=boundary_labels(df,"episode_pred")
    p,r,f,_=precision_recall_fscore_support(y_true,y_pred,average="binary",zero_division=0)
    return {"boundary_precision":float(p),"boundary_recall":float(r),"boundary_f1":float(f)}


def model_complexity(workflows: List[DiscoveredWorkflow]) -> Dict[str,float]:
    if not workflows: return {"workflows":0,"nodes":0,"edges":0,"avg_nodes":0,"avg_edges":0,"forks":0,"joins":0}
    nodes=sum(len(w.nodes) for w in workflows); edges=sum(len(w.edges) for w in workflows)
    forks=joins=0
    for w in workflows:
        f,j=fork_join_signatures(w.nodes,w.edges); forks+=len(f); joins+=len(j)
    return {"workflows":len(workflows),"nodes":nodes,"edges":edges,
            "avg_nodes":nodes/len(workflows),"avg_edges":edges/len(workflows),"forks":forks,"joins":joins}



def episode_membership_metrics(df: pd.DataFrame) -> Dict[str,float]:
    """Order-independent episode partition quality for interleaved/parallel work."""
    if "episode_id_gt" not in df.columns or "episode_pred" not in df.columns:
        return {"episode_ari":np.nan,"episode_nmi":np.nan,"episode_pairwise_f1":np.nan}
    aris=[]; nmis=[]; pair_stats=[]
    for _,g in df.groupby("case_id",sort=False):
        if len(g)<2: continue
        yt=g["episode_id_gt"].astype(str).tolist(); yp=g["episode_pred"].astype(str).tolist()
        aris.append(adjusted_rand_score(yt,yp)); nmis.append(normalized_mutual_info_score(yt,yp))
        tp=fp=fn=0
        for i in range(len(g)):
            for j in range(i+1,len(g)):
                t=yt[i]==yt[j]; p=yp[i]==yp[j]
                tp += int(t and p); fp += int((not t) and p); fn += int(t and (not p))
        pr=tp/(tp+fp) if tp+fp else 0.; rc=tp/(tp+fn) if tp+fn else 0.; f=2*pr*rc/(pr+rc) if pr+rc else 0.
        pair_stats.append(f)
    return {"episode_ari":float(np.mean(aris)) if aris else np.nan,
            "episode_nmi":float(np.mean(nmis)) if nmis else np.nan,
            "episode_pairwise_f1":float(np.mean(pair_stats)) if pair_stats else np.nan}

def tolerant_boundary_metrics(df: pd.DataFrame, tolerance: int=1) -> Dict[str,float]:
    if "episode_id_gt" not in df.columns:
        return {f"tolerant_boundary_precision@{tolerance}":np.nan,f"tolerant_boundary_recall@{tolerance}":np.nan,f"tolerant_boundary_f1@{tolerance}":np.nan}
    tp=fp=fn=0
    for _,g in df.sort_values(["case_id","timestamp"]).groupby("case_id",sort=False):
        gt=[x for x in _boundary_positions(g,"episode_id_gt") if x!=0]; pr=[x for x in _boundary_positions(g,"episode_pred") if x!=0]
        used=set(); matched=0
        for p0 in pr:
            cand=[(abs(p0-g0),j) for j,g0 in enumerate(gt) if j not in used and abs(p0-g0)<=tolerance]
            if cand:
                _,j=min(cand); used.add(j); matched+=1
        tp+=matched; fp+=max(0,len(pr)-matched); fn+=max(0,len(gt)-matched)
    p=tp/(tp+fp) if tp+fp else 0.; r=tp/(tp+fn) if tp+fn else 0.; f=2*p*r/(p+r) if p+r else 0.
    return {f"tolerant_boundary_precision@{tolerance}":p,f"tolerant_boundary_recall@{tolerance}":r,f"tolerant_boundary_f1@{tolerance}":f}


def segmentation_structure_metrics(df: pd.DataFrame) -> Dict[str,float]:
    if "microflow_gt" not in df.columns or "episode_id_gt" not in df.columns:
        return {"segment_purity":np.nan,"fragmentation":np.nan,"merge_rate":np.nan}
    purities=[]; merges=[]; frags=[]
    for _,g in df.sort_values(["case_id","timestamp"]).groupby("case_id",sort=False):
        for _,s in g.groupby("episode_pred",sort=False):
            vc=s["microflow_gt"].value_counts(); purities.append(float(vc.iloc[0]/len(s)) if len(s) else 0.); merges.append(int(s["episode_id_gt"].nunique()))
        for _,s in g.groupby("episode_id_gt",sort=False): frags.append(int(s["episode_pred"].nunique()))
    return {"segment_purity":float(np.mean(purities)) if purities else 0.,"fragmentation":float(np.mean(frags)) if frags else 0.,"merge_rate":float(np.mean(merges)) if merges else 0.}


def window_diff_score(df: pd.DataFrame,k:int=4)->float:
    if "episode_id_gt" not in df.columns: return np.nan
    errors=total=0
    for _,g in df.sort_values(["case_id","timestamp"]).groupby("case_id",sort=False):
        n=len(g)
        if n<=k: continue
        gt=set(x for x in _boundary_positions(g,"episode_id_gt") if x!=0); pr=set(x for x in _boundary_positions(g,"episode_pred") if x!=0)
        for start in range(0,n-k):
            end=start+k; ng=sum(1 for b in gt if start<b<=end); npred=sum(1 for b in pr if start<b<=end)
            errors+=int(ng!=npred); total+=1
    return errors/total if total else 0.


def _boundary_positions(g,episode_col):
    vals=g[episode_col].tolist(); pos=[0] if vals else []
    for i in range(1,len(vals)):
        if vals[i]!=vals[i-1]: pos.append(i)
    return pos
