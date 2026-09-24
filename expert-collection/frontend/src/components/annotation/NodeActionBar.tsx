// Actions for the node selected on the graph. Replaces the old per-node text list: the
// annotator clicks a node *on the DAG* and judges it here. "合并" offers only the node's real
// graph predecessors (the old "merge into the previous node in the list" picked a non-adjacent
// node whenever the graph branched). In Rework mode it additionally offers rename / insert.
import { useEffect, useState, type CSSProperties } from "react";
import type { Graph, GraphNode } from "../../api/types";
import { DELETE_COLOR, MERGE_COLOR, parseVerdict, predecessors } from "../../utils/annotationAccess";

const chip = (active: boolean, color = "#2a78d6"): CSSProperties => ({
  border: `1px solid ${active ? color : "#d0d5dd"}`,
  color: active ? color : "#475569",
  background: active ? `${color}14` : "#fff",
  borderRadius: 6, padding: "4px 10px", fontSize: 12, cursor: "pointer",
});

export function NodeActionBar({
  graph, node, verdict, onVerdict, rework, onClose,
}: {
  graph: Graph;
  node: GraphNode;
  verdict: string | undefined;
  onVerdict: (v: string) => void;
  // Rework-only extras; omitted in review mode.
  rework?: {
    rename: string | undefined;
    onRename: (label: string | null) => void; // null clears the rename
    onInsertAfter: (label: string) => void;
  };
  onClose: () => void;
}) {
  const terminal = node.node_type === "start" || node.node_type === "end";
  const branching = node.node_type === "decision" || node.node_type === "parallel_split";
  const preds = predecessors(graph, node.node_id);
  const current = parseVerdict(verdict);
  const [renameDraft, setRenameDraft] = useState(rework?.rename ?? "");
  const [insertDraft, setInsertDraft] = useState("");

  useEffect(() => {
    setRenameDraft(rework?.rename ?? "");
    setInsertDraft("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [node.node_id]);

  return (
    <div style={{ border: "1px solid #bfd4f2", background: "#f6f9fe", borderRadius: 8, padding: "10px 12px", marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <div style={{ fontSize: 12.5, fontWeight: 700 }}>
          节点「{node.label}」
          {terminal && <span style={{ fontWeight: 400, color: "#94a3b8", marginLeft: 6 }}>开始/结束节点不能删除或合并</span>}
        </div>
        <button onClick={onClose} style={{ border: "none", background: "none", color: "#94a3b8", cursor: "pointer", fontSize: 12 }}>
          收起
        </button>
      </div>

      {!terminal && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          <button onClick={() => onVerdict("keep")} style={chip(current.kind === "keep")}>保留</button>
          <button onClick={() => onVerdict("delete")} style={chip(current.kind === "delete", DELETE_COLOR)}>删除</button>
          {preds.map((p) => (
            <button
              key={p.node_id}
              onClick={() => onVerdict(`merge_into:${p.node_id}`)}
              style={chip(current.kind === "merge_into" && current.target === p.node_id, MERGE_COLOR)}
            >
              合并进「{p.label}」
            </button>
          ))}
        </div>
      )}

      {rework && (
        <div style={{ marginTop: 10, display: "grid", gap: 6 }}>
          {current.kind === "keep" && (
            <div style={{ display: "flex", gap: 6 }}>
              <input
                value={renameDraft}
                onChange={(e) => setRenameDraft(e.target.value)}
                placeholder={`改名（当前：${node.label}）`}
                style={{ flex: 1, border: "1px solid #d0d5dd", borderRadius: 6, padding: "5px 8px", fontSize: 12 }}
              />
              {/* Empty draft + an existing rename = clear it; empty draft + no rename = nothing to do. */}
              <button
                disabled={!renameDraft.trim() && !rework.rename}
                onClick={() => rework.onRename(renameDraft.trim() ? renameDraft.trim() : null)}
                style={{ ...chip(false), opacity: !renameDraft.trim() && !rework.rename ? 0.5 : 1 }}
              >
                {!renameDraft.trim() && rework.rename ? "取消改名" : "应用改名"}
              </button>
            </div>
          )}
          {node.node_type !== "end" && current.kind !== "delete" && (
            branching ? (
              <div style={{ fontSize: 11.5, color: "#94a3b8" }}>这是分支/并行拆分节点，要补步骤请点具体某条分支上的节点，在它之后插入</div>
            ) : (
              <div style={{ display: "flex", gap: 6 }}>
                <input
                  value={insertDraft}
                  onChange={(e) => setInsertDraft(e.target.value)}
                  placeholder="在此节点之后插入一个步骤（步骤缺失时用）"
                  style={{ flex: 1, border: "1px solid #d0d5dd", borderRadius: 6, padding: "5px 8px", fontSize: 12 }}
                />
                <button
                  disabled={!insertDraft.trim()}
                  onClick={() => {
                    rework.onInsertAfter(insertDraft.trim());
                    setInsertDraft("");
                  }}
                  style={{ ...chip(false), opacity: insertDraft.trim() ? 1 : 0.5 }}
                >
                  插入
                </button>
              </div>
            )
          )}
        </div>
      )}
    </div>
  );
}
