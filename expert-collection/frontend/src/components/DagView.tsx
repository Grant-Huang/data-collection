// DAG rendering: React Flow for interaction, elkjs for auto-layout, styled to match
// docs/expert-workflow-collection/design/dag-view-redesign.html's palette (PRD section 11.3)
// so the working app visually matches the approved prototype rather than diverging from it.
import { useEffect, useMemo, useRef, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  Handle,
  Position,
  type Edge as RFEdge,
  type Node as RFNode,
  type ReactFlowInstance,
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

// Optional per-node overlay (annotation panel: node verdict colors, arbitration diff
// highlight, selected node). Purely visual -- doesn't affect layout.
export interface NodeDecoration {
  border?: string; // replaces the node-type stroke color
  badge?: string; // small tag rendered above the node, e.g. "删除"
  badgeColor?: string;
  faded?: boolean; // e.g. a node marked for deletion
  selected?: boolean;
}

interface WorkflowNodeData {
  label: string;
  nodeType: NodeType;
  confirmed: boolean;
  hasRetry: boolean;
  highlighted?: boolean; // hovering a chat message's "图上 +N" tag
  decoration?: NodeDecoration;
  clickable?: boolean;
  // Section 17 evidence: quotes backing the step; "unverified" = graph built from a
  // narration but this step's quote wasn't found in what the expert said.
  evidence?: string[];
  unverified?: boolean;
  // Second line under the label (task-layer tab: owner / step count).
  subtitle?: string;
}

function WorkflowNode({ data }: { data: WorkflowNodeData }) {
  const style = NODE_STYLE[data.nodeType] ?? NODE_STYLE.activity;
  const radius = style.shape === "pill" ? 999 : style.shape === "diamond" ? 10 : 8;
  const deco = data.decoration;
  return (
    <div
      title={data.evidence?.length ? `依据原话：「${data.evidence.join("」「")}」` : data.unverified ? "没有在讲述中找到这一步的原话，待确认" : undefined}
      style={{
        background: style.fill,
        border: `${deco?.border || deco?.selected ? 2.4 : 1.6}px ${data.unverified && !deco?.border ? "dashed" : "solid"} ${deco?.selected ? "#2a78d6" : deco?.border ?? (data.unverified ? "#f59e0b" : style.stroke)}`,
        opacity: deco?.faded ? 0.5 : 1,
        textDecoration: deco?.faded ? "line-through" : undefined,
        cursor: data.clickable ? "pointer" : undefined,
        borderRadius: radius,
        padding: "10px 16px",
        minWidth: 120,
        maxWidth: 220,
        fontSize: 12.5,
        fontWeight: 700,
        color: "#1f2937",
        textAlign: "center",
        // Highlight (hovering a chat message's "图上 +N" tag) wins over the confirmed ring.
        boxShadow: data.highlighted
          ? "0 0 0 3px #f59e0b88"
          : data.confirmed
            ? "0 0 0 2px #0ca30c33"
            : "none",
        transition: "box-shadow 0.15s",
        position: "relative",
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      {deco?.badge && (
        <div
          style={{
            position: "absolute", top: -10, left: "50%", transform: "translateX(-50%)", whiteSpace: "nowrap",
            background: deco.badgeColor ?? "#2a78d6", color: "#fff", borderRadius: 999, padding: "1px 8px",
            fontSize: 10.5, fontWeight: 700, textDecoration: "none",
          }}
        >
          {deco.badge}
        </div>
      )}
      {data.label}
      {data.subtitle && (
        <div style={{ fontSize: 11, fontWeight: 500, color: "#667085", marginTop: 3 }}>{data.subtitle}</div>
      )}
      {data.hasRetry && (
        <div style={{ position: "absolute", top: -8, right: -8, fontSize: 14 }} title="有返工语义（retry_semantics）">
          ↺
        </div>
      )}
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </div>
  );
}

const nodeTypes = { workflow: WorkflowNode };

async function layout(graph: Graph): Promise<{ nodes: RFNode[]; edges: RFEdge[]; width: number; height: number }> {
  const elkGraph = {
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      // Top-to-bottom reads more naturally for a step-by-step manufacturing workflow and
      // matches how the expert narrates it (this step, then that step...).
      "elk.direction": "DOWN",
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

  return { nodes: rfNodes, edges: rfEdges, width: result.width ?? 800, height: result.height ?? 600 };
}

interface DagViewProps {
  graph: Graph;
  onNodeTap?: (node: GraphNode) => void;
  readOnly?: boolean;
  emptyLabel?: string;
  // When true, the canvas is sized to exactly fit the laid-out graph (no internal fitView
  // zoom) and its own pan/zoom gestures are disabled, so the *page* scrolls to reveal the
  // rest of a tall graph instead of the graph panning inside a fixed viewport. Used by the
  // mobile DAG page, which reads top-to-bottom and scrolls like the rest of the page.
  scrollable?: boolean;
  // Nodes to emphasize (e.g. what the latest conversation turn added). Display-only; does
  // not trigger a re-layout.
  highlightNodeIds?: string[] | null;
  nodeDecorations?: Record<string, NodeDecoration>;
  // Optional second line under a node's label, keyed by node_id -- used by the task-layer tab
  // to show each task's owner / step count without changing the node label itself.
  subtitles?: Record<string, string>;
}

export function DagView({ graph, onNodeTap, readOnly, emptyLabel, scrollable, highlightNodeIds, nodeDecorations, subtitles }: DagViewProps) {
  const [nodes, setNodes] = useState<RFNode[]>([]);
  const [edges, setEdges] = useState<RFEdge[]>([]);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const containerRef = useRef<HTMLDivElement>(null);
  const flowInstance = useRef<ReactFlowInstance | null>(null);
  const nodeCount = graph.nodes.length;

  // Re-layout whenever the graph's content changes. Counts alone are not enough: the guide's
  // structural questions rewire existing edges and fill in branch conditions / approver
  // labels without changing how many nodes or edges there are, and a rework preview can
  // merge one node and insert another. Decorations are applied in `displayNodes` below
  // without re-running ELK.
  const layoutKey = useMemo(
    () =>
      [
        ...graph.nodes.map((n) => `${n.node_id}:${n.node_type}:${n.label}:${n.retry_semantics?.enabled ? 1 : 0}:${n.expert_confirmed ? 1 : 0}`),
        ...graph.edges.map((e) => `${e.edge_id}:${e.from}>${e.to}:${e.edge_type}:${e.condition ?? ""}`),
      ].join("|"),
    [graph],
  );

  useEffect(() => {
    let cancelled = false;
    layout(graph).then((res) => {
      if (!cancelled) {
        setNodes(res.nodes);
        setEdges(res.edges);
        setSize({ width: res.width, height: res.height });
      }
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layoutKey]);

  // Apply highlight on top of the laid-out nodes without re-running ELK.
  const highlightKey = (highlightNodeIds ?? []).join(",");
  useEffect(() => {
    const ids = new Set(highlightNodeIds ?? []);
    setNodes((prev) => prev.map((n) => ({ ...n, data: { ...n.data, highlighted: ids.has(n.id) } })));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlightKey, layoutKey]);

  const [containerWidth, setContainerWidth] = useState(0);
  useEffect(() => {
    if (!scrollable || !containerRef.current) return;
    const el = containerRef.current;
    const observer = new ResizeObserver((entries) => setContainerWidth(entries[0].contentRect.width));
    observer.observe(el);
    setContainerWidth(el.clientWidth);
    return () => observer.disconnect();
  }, [scrollable]);

  // Scrollable (mobile) mode: scale the graph down so its full width always fits the
  // container -- no horizontal scrolling, only vertical (PRD-requested top-down + scroll).
  const fitZoom = scrollable && containerWidth > 0 && size.width > 0 ? Math.min(1, (containerWidth - 32) / size.width) : 1;

  useEffect(() => {
    if (!scrollable || !flowInstance.current || size.width === 0) return;
    const scaledWidth = size.width * fitZoom;
    const x = Math.max(16, (containerWidth - scaledWidth) / 2);
    flowInstance.current.setViewport({ x, y: 20, zoom: fitZoom });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scrollable, fitZoom, containerWidth, size.width, layoutKey]);

  const displayNodes = useMemo(() => {
    const byId = new Map(graph.nodes.map((n) => [n.node_id, n]));
    // Only graphs built by the review loop carry evidence; don't flag every node of an
    // imported / step-by-step graph as "unverified" just because it has none.
    const tracksEvidence = graph.nodes.some((n) => (n.evidence?.length ?? 0) > 0);
    return nodes.map((n) => {
      const src = byId.get(n.id);
      const evidence = src?.evidence ?? [];
      return {
      ...n,
      data: {
        ...n.data,
        evidence,
        unverified: tracksEvidence && evidence.length === 0 && src?.node_type !== "start" && src?.node_type !== "end",
        label: src?.label ?? n.data.label,
        decoration: nodeDecorations?.[n.id],
        clickable: !!onNodeTap,
        subtitle: subtitles?.[n.id],
      },
      };
    });
  }, [nodes, graph, nodeDecorations, onNodeTap, subtitles]);

  if (nodeCount === 0) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#667085", fontSize: 13, padding: 24, textAlign: "center" }}>
        {emptyLabel ?? "流程图会随着对话逐步生成，先在左侧回答第一个问题吧。"}
      </div>
    );
  }

  const flow = (
    <ReactFlow
      nodes={displayNodes}
      edges={edges}
      nodeTypes={nodeTypes}
      fitView={!scrollable}
      defaultViewport={scrollable ? { x: 20, y: 20, zoom: 1 } : undefined}
      onInit={(instance) => {
        flowInstance.current = instance;
      }}
      proOptions={{ hideAttribution: true }}
      nodesDraggable={!readOnly && !scrollable}
      nodesConnectable={false}
      elementsSelectable={!readOnly}
      panOnDrag={!scrollable}
      zoomOnScroll={!scrollable}
      zoomOnPinch={!scrollable}
      zoomOnDoubleClick={!scrollable}
      minZoom={0.3}
      maxZoom={3}
      onNodeClick={(_, node) => {
        const original = graph.nodes.find((n) => n.node_id === node.id);
        if (original) onNodeTap?.(original);
      }}
    >
      <Background color="#e5e7eb" gap={20} />
      {!readOnly && !scrollable && <Controls showInteractive={false} />}
    </ReactFlow>
  );

  if (scrollable) {
    return (
      <div ref={containerRef} style={{ width: "100%", height: size.height * fitZoom + 40, minHeight: 200 }}>
        {flow}
      </div>
    );
  }
  return flow;
}
