// Dual-DAG panel (IMPLEMENTATION_PLAN.md section 18): one expert conversation produces two
// graphs, shown as two independent tabs --
//   「任务协作」 = task_workflow.graph, the upper layer ("谁负责哪一段、怎么交接")
//   「SOP 步骤」 = graph, the step layer ("每一段具体怎么做"; this is the graph that existed before)
// The tabs deliberately don't link to each other (product decision): clicking a task does not
// jump to or filter the SOP tab. Shared by the desktop right panel and the mobile DAG page.
import { useMemo, useState, type ReactNode } from "react";
import type { GraphNode, WorkflowRecord } from "../api/types";
import { DagView } from "./DagView";

export type DagTab = "task" | "sop";

// Same set as backend task_layer._STEP_NODE_TYPES: nodes carrying expert-described content.
const STEP_NODE_TYPES = new Set(["activity", "approval", "wait", "handoff"]);

const TASK_STAGES = new Set(["task_outline", "task_boundary"]);

interface Props {
  active: WorkflowRecord;
  // Mobile passes readOnly + scrollable, same as it did for the single DagView before.
  readOnly?: boolean;
  scrollable?: boolean;
  onNodeTap?: (node: GraphNode, tab: DagTab) => void;
  sopEmptyLabel?: string;
  // Nodes the latest conversation turn added (desktop chat hover) -- SOP tab only.
  sopHighlightNodeIds?: string[] | null;
  // Rendered under the graph for the current tab (mobile puts its stats/rules sections here).
  footer?: (tab: DagTab) => ReactNode;
}

export function DualDagPanel({ active, readOnly, scrollable, onNodeTap, sopEmptyLabel, sopHighlightNodeIds, footer }: Props) {
  // Default to the SOP tab: it's the one that fills in live while the expert is talking; the
  // task layer only appears at the very end of the conversation.
  const [tab, setTab] = useState<DagTab>("sop");

  // "负责：质量部 · 3 个步骤" under each task node -- read off the task's own owner and the
  // size of its mapped SOP segment, nothing inferred.
  const taskSubtitles = useMemo(() => {
    const tw = active.task_workflow;
    if (!tw) return undefined;
    const stepIds = new Set(active.graph.nodes.filter((n) => STEP_NODE_TYPES.has(n.node_type)).map((n) => n.node_id));
    const out: Record<string, string> = {};
    for (const t of tw.tasks) {
      const node = tw.graph.nodes.find((n) => n.node_id === t.task_id);
      const owner = node?.actor_roles[0];
      const steps = t.sop_node_ids.filter((id) => stepIds.has(id)).length;
      out[t.task_id] = [owner ? `负责：${owner}` : "负责方未说明", steps > 0 ? `${steps} 个步骤` : "未描述步骤"].join(" · ");
    }
    return out;
  }, [active]);

  const taskEmptyLabel = TASK_STAGES.has(active.stage)
    ? "正在划分任务……回答完会话里的问题，这里就会出现任务协作图。"
    : active.stage.startsWith("review_")
      // Section 17 "先讲述、后评审" loop (review_agent) doesn't produce a task layer yet.
      ? "这个会话用「先讲述、后评审」方式采集，暂不生成任务协作图。"
      : active.status === "expert_confirmed" || active.stage === "review"
      ? "这个会话是在任务协作层上线之前采集的，没有任务协作图。"
      : "任务协作图会在对话最后生成：步骤讲完后，会请你按「谁负责哪一段」划分任务。";

  const tabButton = (value: DagTab, label: string) => (
    <button
      key={value}
      role="tab"
      aria-selected={tab === value}
      onClick={() => setTab(value)}
      style={{
        border: "none",
        background: "none",
        padding: "10px 4px",
        marginRight: 16,
        minHeight: 40,
        fontSize: 13,
        fontWeight: tab === value ? 700 : 500,
        color: tab === value ? "#1f2937" : "#667085",
        borderBottom: `2px solid ${tab === value ? "#2a78d6" : "transparent"}`,
        cursor: "pointer",
      }}
    >
      {label}
    </button>
  );

  const graphArea =
    tab === "task" ? (
      active.task_workflow ? (
        <DagView
          key={`task-${active.id}`}
          graph={active.task_workflow.graph}
          readOnly={readOnly}
          scrollable={scrollable}
          subtitles={taskSubtitles}
          onNodeTap={onNodeTap ? (n) => onNodeTap(n, "task") : undefined}
        />
      ) : (
        <EmptyHint text={taskEmptyLabel} />
      )
    ) : active.graph.nodes.length === 0 && !scrollable ? (
      // Scenario/Case Context questions (IMPLEMENTATION_PLAN.md section 9.1) come before any
      // graph node exists -- show that this is expected, not a stuck app.
      <EmptyHint text={active.stage === "review_narrative" ? "您讲完之后，这里会生成流程图" : "背景信息收集中，还没开始画图……"} />
    ) : (
      <DagView
        key={`sop-${active.id}`}
        graph={active.graph}
        readOnly={readOnly}
        scrollable={scrollable}
        emptyLabel={sopEmptyLabel}
        highlightNodeIds={sopHighlightNodeIds}
        onNodeTap={onNodeTap ? (n) => onNodeTap(n, "sop") : undefined}
      />
    );

  return (
    <div style={{ display: "flex", flexDirection: "column", height: scrollable ? undefined : "100%" }}>
      <div role="tablist" style={{ display: "flex", padding: "0 14px", borderBottom: "1px solid #e5e7eb", flexShrink: 0 }}>
        {tabButton("task", "任务协作")}
        {tabButton("sop", "SOP 步骤")}
      </div>
      <div style={scrollable ? { minHeight: 160 } : { flex: 1, minHeight: 0 }}>{graphArea}</div>
      {footer?.(tab)}
    </div>
  );
}

function EmptyHint({ text }: { text: string }) {
  return (
    <div style={{ height: "100%", minHeight: 160, display: "flex", alignItems: "center", justifyContent: "center", color: "#94a3b8", fontSize: 12.5, textAlign: "center", padding: 24 }}>
      {text}
    </div>
  );
}
