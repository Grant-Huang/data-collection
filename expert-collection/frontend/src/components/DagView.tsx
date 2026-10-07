// DAG rendering: React Flow for interaction, elkjs for auto-layout, styled to match
// docs/expert-workflow-collection/design/dag-view-redesign.html's palette (PRD section 11.3)
// so the working app visually matches the approved prototype rather than diverging from it.
import type ELK from "elkjs/lib/elk.bundled.js";
import { useEffect, useMemo, useRef, useState, memo } from "react";
import ReactFlow, {
  Background,
  Controls,
  Handle,
  Position,
  type Edge as RFEdge,
  type Node as RFNode,
  type ReactFlowInstance,
  MarkerType,
  type NodeProps,
  type NodeChange,
  applyNodeChanges,
} from "reactflow";
import "reactflow/dist/style.css";
import type { Graph, GraphNode, NodeType } from "../api/types";
import { ontologyFacets, ontologyTooltip } from "../utils/ontologyFacets";

// elkjs is by far the biggest dependency (~1.4 MB unminified) and only needed once there is a
// graph to lay out, so it is fetched on first use instead of with the page (C2) -- the chat
// column renders and accepts input while it loads. One shared instance.
// (The type-only import below is erased at build time; it doesn't pull the library in.)
type ElkInstance = InstanceType<typeof ELK>;
let elkPromise: Promise<ElkInstance> | null = null;
function getElk(): Promise<ElkInstance> {
  elkPromise ??= import("elkjs/lib/elk.bundled.js").then((m) => new m.default());
  return elkPromise;
}

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
  // Stable step number (Node.seq) -- shown so a person can say "第3步" and mean exactly this
  // node, and the review-loop model is told the same number (review_agent._graph_for_prompt).
  seq?: number | null;
  // Ontology dimensions captured on this step (threshold / time limit / escalation), as short
  // tags under the label; `ontologyNotes` are the expert's verbatim answers for the tooltip.
  facets?: string[];
  ontologyNotes?: string[];
  // Schema attributes for tooltip display
  actorRoles?: string[];
  decisionQuestion?: string | null;
  confidence?: number;
  retrySemantics?: { condition: string | null; description: string | null } | null;
}

// Extra ELK height for a node that shows a row of ontology tags, so tags never overlap the
// next layer.
const FACET_ROW_HEIGHT = 20;

const WorkflowNode = memo(function WorkflowNode({ data, dragging }: NodeProps<WorkflowNodeData>) {
  const style = NODE_STYLE[data.nodeType] ?? NODE_STYLE.activity;
  const radius = style.shape === "pill" ? 999 : style.shape === "diamond" ? 10 : 8;
  const deco = data.decoration;
  const isDragging = dragging ?? false;

  const buildTooltip = () => {
    const parts: string[] = [];

    if (data.evidence?.length) {
      parts.push(`依据原话：「${data.evidence.join("」「")}」`);
    } else if (data.unverified) {
      parts.push("没有在讲述中找到这一步的原话，待确认");
    }

    if (data.actorRoles?.length) {
      parts.push(`角色：${data.actorRoles.join("、")}`);
    }

    if (data.decisionQuestion) {
      parts.push(`决策问题：${data.decisionQuestion}`);
    }

    if (data.confidence !== undefined) {
      const confStr = (data.confidence * 100).toFixed(0);
      parts.push(`信心度：${confStr}%`);
    }

    if (data.retrySemantics?.condition || data.retrySemantics?.description) {
      const retryParts = [];
      if (data.retrySemantics.condition) {
        retryParts.push(`返工条件：${data.retrySemantics.condition}`);
      }
      if (data.retrySemantics.description) {
        retryParts.push(`说明：${data.retrySemantics.description}`);
      }
      parts.push(retryParts.join("\n"));
    }

    // Ontology follow-up answers (threshold / time limit / escalation), expert's own words.
    parts.push(...(data.ontologyNotes ?? []));

    return parts.length > 0 ? parts.join("\n") : undefined;
  };

  return (
    <div
      title={buildTooltip()}
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
        boxShadow: isDragging
          ? "0 0 0 3px #2a78d688, 0 8px 16px rgba(42, 120, 214, 0.3)"
          : data.highlighted
            ? "0 0 0 3px #f59e0b88, 0 4px 12px rgba(0,0,0,0.15)"
            : data.confirmed
              ? "0 0 0 2px #0ca30c33, 0 2px 8px rgba(0,0,0,0.08)"
              : "0 1px 3px rgba(0,0,0,0.05)",
        transition: "box-shadow 0.15s, opacity 0.15s",
        position: "relative",
        willChange: "transform",
        zIndex: isDragging ? 1000 : undefined,
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      {data.seq != null && (
        <div
          title={`第 ${data.seq} 步`}
          style={{
            position: "absolute", top: -9, left: -9, width: 20, height: 20, borderRadius: "50%",
            background: "#fff", border: `1.4px solid ${deco?.border ?? (data.unverified ? "#f59e0b" : style.stroke)}`,
            color: "#475569", fontSize: 10.5, fontWeight: 700, lineHeight: "18px", textAlign: "center",
          }}
        >
          {data.seq}
        </div>
      )}
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
      {!!data.facets?.length && (
        <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 4, marginTop: 5 }}>
          {data.facets.map((f) => (
            <span
              key={f}
              style={{
                fontSize: 10.5, fontWeight: 600, color: "#475569", background: "#f1f5f9",
                border: "1px solid #e2e8f0", borderRadius: 999, padding: "0 6px", lineHeight: "16px",
                whiteSpace: "nowrap", textDecoration: "none",
              }}
            >
              {f}
            </span>
          ))}
        </div>
      )}
      {data.hasRetry && (
        <div style={{ position: "absolute", top: -8, right: -8, fontSize: 14 }} title="有返工语义（retry_semantics）">
          ↺
        </div>
      )}
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </div>
  );
});

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
    children: graph.nodes.map((n) => ({
      id: n.node_id, width: 230, height: 70 + (ontologyFacets(n).length ? FACET_ROW_HEIGHT : 0),
    })),
    edges: graph.edges.map((e) => ({ id: e.edge_id, sources: [e.from], targets: [e.to] })),
  };
  const result = await (await getElk()).layout(elkGraph);
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
      seq: n.seq,
      actorRoles: n.actor_roles,
      decisionQuestion: n.decision_question,
      confidence: n.confidence,
      retrySemantics: n.retry_semantics ? { condition: n.retry_semantics.condition, description: n.retry_semantics.description } : null,
    },
  }));

  const EDGE_COLOR: Record<string, string> = {
    normal: "#94a3b8", conditional: "#f59e0b", parallel: "#8b5cf6",
    merge: "#3b82f6", approval: "#10b981", handoff: "#f97316",
    timeout: "#94a3b8", exception_forward: "#ef4444",
  };

  const rfEdges: RFEdge[] = graph.edges.map((e) => {
    const targetNode = nodeById.get(e.to);
    const isConfirmed = targetNode?.expert_confirmed;
    return {
      id: e.edge_id,
      source: e.from,
      target: e.to,
      label: e.condition ?? undefined,
      // Only animate conditional edges to target unconfirmed nodes, reduces animation overhead
      animated: !isConfirmed && e.edge_type === "conditional",
      style: { stroke: EDGE_COLOR[e.edge_type] ?? "#94a3b8", strokeWidth: 1.6 },
      markerEnd: { type: MarkerType.ArrowClosed, color: EDGE_COLOR[e.edge_type] ?? "#94a3b8" },
      labelStyle: { fontSize: 11, fill: "#667085" },
    };
  });

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
  // Fires once when a manual drag ends (not on every intermediate mouse move). The caller
  // persists it as that node's `manual_position`; see the layout() call above for how a saved
  // manual_position wins over ELK's own answer on every future layout. Only reachable when
  // dragging is actually enabled (!readOnly && !scrollable), so this is the one and only path
  // that can move a node -- an LLM-driven edit never can (review_agent.sanitize_ops's
  // update_node patch whitelist doesn't include position).
  onNodeMove?: (nodeId: string, position: { x: number; y: number }) => void;
  // Optional second line under a node's label, keyed by node_id -- used by the task-layer tab
  // to show each task's owner / step count without changing the node label itself.
  subtitles?: Record<string, string>;
}

export function DagView({
  graph, onNodeTap, readOnly, emptyLabel, scrollable, highlightNodeIds, nodeDecorations, onNodeMove, subtitles,
}: DagViewProps) {
  const [nodes, setNodes] = useState<RFNode[]>([]);
  const [edges, setEdges] = useState<RFEdge[]>([]);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const containerRef = useRef<HTMLDivElement>(null);
  const flowInstance = useRef<ReactFlowInstance | null>(null);
  const layoutCacheRef = useRef<{ key: string; result: Awaited<ReturnType<typeof layout>> } | null>(null);
  const nodeCount = graph.nodes.length;

  // Re-layout whenever the graph's content changes. Counts alone are not enough: the guide's
  // structural questions rewire existing edges and fill in branch conditions / approver
  // labels without changing how many nodes or edges there are, and a rework preview can
  // merge one node and insert another. Decorations are applied in `displayNodes` below
  // without re-running ELK.
  const layoutKey = useMemo(
    () =>
      [
        ...graph.nodes.map((n) => `${n.node_id}:${n.node_type}:${n.label}:${n.retry_semantics?.enabled ? 1 : 0}:${n.expert_confirmed ? 1 : 0}:${ontologyFacets(n).length ? 1 : 0}`),
        ...graph.edges.map((e) => `${e.edge_id}:${e.from}>${e.to}:${e.edge_type}:${e.condition ?? ""}`),
      ].join("|"),
    [graph],
  );

  useEffect(() => {
    let cancelled = false;

    // Check cache first to avoid redundant layout calculations
    if (layoutCacheRef.current?.key === layoutKey) {
      const res = layoutCacheRef.current.result;
      setNodes(res.nodes);
      setEdges(res.edges);
      setSize({ width: res.width, height: res.height });
      return;
    }

    layout(graph).then((res) => {
      if (!cancelled) {
        layoutCacheRef.current = { key: layoutKey, result: res };
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
        seq: src?.seq,
        facets: src ? ontologyFacets(src) : [],
        ontologyNotes: src ? ontologyTooltip(src) : [],
        actorRoles: src?.actor_roles,
        decisionQuestion: src?.decision_question,
        confidence: src?.confidence,
        retrySemantics: src?.retry_semantics ? { condition: src.retry_semantics.condition, description: src.retry_semantics.description } : null,
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
      // Performance optimizations: only pan on drag if not in read-only mode
      // and prevent selection box from appearing during panning
      selectNodesOnDrag={false}
      onNodeClick={(_, node) => {
        const original = graph.nodes.find((n) => n.node_id === node.id);
        if (original) onNodeTap?.(original);
      }}
      // React Flow v11 in controlled mode only moves a node if its changes are applied back
      // into `nodes`; without this the dragged node never moved on screen at all (verified in
      // a browser run: same coordinates before and after a drag). Only position/dimension/
      // selection changes reach here -- nodes are never added or removed by React Flow itself.
      onNodesChange={(changes: NodeChange[]) => setNodes((prev) => applyNodeChanges(changes, prev))}
      onNodeDragStop={(_, node) => {
        onNodeMove?.(node.id, node.position);
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
