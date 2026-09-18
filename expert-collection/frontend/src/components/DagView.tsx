// DAG rendering: React Flow for interaction, elkjs for auto-layout, styled to match
// docs/expert-workflow-collection/design/dag-view-redesign.html's palette (PRD section 11.3)
// so the working app visually matches the approved prototype rather than diverging from it.
import { useEffect, useMemo, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  Handle,
  Position,
  type Edge as RFEdge,
  type Node as RFNode,
  MarkerType,
} from "reactflow";
import "reactflow/dist/style.css";
import ELK from "elkjs/lib/elk.bundled.js";
import type { Graph, GraphNode, NodeType } from "../api/types";

const elk = new ELK();

const NODE_STYLE: Record<NodeType, { fill: string; stroke: string; shape: "pill" | "rect" | "diamond" | "hex" }> = {
  start: { fill: "#f8fafc", stroke: "#94a3b8", shape: "pill" },
  end: { fill: "#f8fafc", stroke: "#94a3b8", shape: "pill" },
  activity: { fill: "#ffffff", stroke: "#cbd5e1", shape: "rect" },
  wait: { fill: "#ffffff", stroke: "#cbd5e1", shape: "rect" },
  decision: { fill: "#fffbeb", stroke: "#f59e0b", shape: "diamond" },
  parallel_split: { fill: "#f5f3ff", stroke: "#8b5cf6", shape: "hex" },
  parallel_join: { fill: "#f5f3ff", stroke: "#8b5cf6", shape: "hex" },
  merge: { fill: "#eff6ff", stroke: "#3b82f6", shape: "hex" },
  approval: { fill: "#ecfdf5", stroke: "#10b981", shape: "rect" },
  handoff: { fill: "#fff7ed", stroke: "#f97316", shape: "rect" },
};

function WorkflowNode({ data }: { data: { label: string; nodeType: NodeType; confirmed: boolean; hasRetry: boolean } }) {
  const style = NODE_STYLE[data.nodeType];
  const radius = style.shape === "pill" ? 999 : style.shape === "diamond" ? 10 : 8;
  return (
    <div
      style={{
        background: style.fill,
        border: `1.6px solid ${style.stroke}`,
        borderRadius: radius,
        padding: "10px 16px",
        minWidth: 120,
        maxWidth: 220,
        fontSize: 12.5,
        fontWeight: 700,
        color: "#1f2937",
        textAlign: "center",
        boxShadow: data.confirmed ? "0 0 0 2px #0ca30c33" : "none",
        position: "relative",
      }}
    >
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      {data.label}
      {data.hasRetry && (
        <div style={{ position: "absolute", top: -8, right: -8, fontSize: 14 }} title="有返工语义（retry_semantics）">
          ↺
        </div>
      )}
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </div>
  );
}

const nodeTypes = { workflow: WorkflowNode };

async function layout(graph: Graph): Promise<{ nodes: RFNode[]; edges: RFEdge[] }> {
  const elkGraph = {
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "RIGHT",
      "elk.spacing.nodeNode": "50",
      "elk.layered.spacing.nodeNodeBetweenLayers": "90",
    },
    children: graph.nodes.map((n) => ({ id: n.node_id, width: 230, height: 70 })),
    edges: graph.edges.map((e) => ({ id: e.edge_id, sources: [e.from], targets: [e.to] })),
  };
  const result = await elk.layout(elkGraph);
  const posById = new Map((result.children ?? []).map((c) => [c.id, { x: c.x ?? 0, y: c.y ?? 0 }]));

  const nodeById = new Map<string, GraphNode>(graph.nodes.map((n) => [n.node_id, n]));

  const rfNodes: RFNode[] = graph.nodes.map((n) => ({
    id: n.node_id,
    type: "workflow",
    position: n.manual_position ?? posById.get(n.node_id) ?? { x: 0, y: 0 },
    data: {
      label: n.label,
      nodeType: n.node_type,
      confirmed: n.expert_confirmed,
      hasRetry: !!n.retry_semantics?.enabled,
    },
  }));

  const EDGE_COLOR: Record<string, string> = {
    normal: "#94a3b8", conditional: "#f59e0b", parallel: "#8b5cf6",
    merge: "#3b82f6", approval: "#10b981", handoff: "#f97316",
    timeout: "#94a3b8", exception_forward: "#ef4444",
  };

  const rfEdges: RFEdge[] = graph.edges.map((e) => ({
    id: e.edge_id,
    source: e.from,
    target: e.to,
    label: e.condition ?? undefined,
    animated: !nodeById.get(e.to)?.expert_confirmed,
    style: { stroke: EDGE_COLOR[e.edge_type] ?? "#94a3b8", strokeWidth: 1.6 },
    markerEnd: { type: MarkerType.ArrowClosed, color: EDGE_COLOR[e.edge_type] ?? "#94a3b8" },
    labelStyle: { fontSize: 11, fill: "#667085" },
  }));

  return { nodes: rfNodes, edges: rfEdges };
}

export function DagView({ graph }: { graph: Graph }) {
  const [nodes, setNodes] = useState<RFNode[]>([]);
  const [edges, setEdges] = useState<RFEdge[]>([]);
  const nodeCount = graph.nodes.length;
  const edgeCount = graph.edges.length;

  // Re-layout whenever the graph's shape changes; keying off node/edge counts (rather than
  // deep-equality) is enough here since the mock guide service only ever appends structure.
  const layoutKey = useMemo(() => `${nodeCount}-${edgeCount}`, [nodeCount, edgeCount]);

  useEffect(() => {
    let cancelled = false;
    layout(graph).then((res) => {
      if (!cancelled) {
        setNodes(res.nodes);
        setEdges(res.edges);
      }
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layoutKey]);

  if (nodeCount === 0) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#667085", fontSize: 13 }}>
        流程图会随着对话逐步生成，先在左侧回答第一个问题吧。
      </div>
    );
  }

  return (
    <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView proOptions={{ hideAttribution: true }}>
      <Background color="#e5e7eb" gap={20} />
      <Controls showInteractive={false} />
    </ReactFlow>
  );
}
