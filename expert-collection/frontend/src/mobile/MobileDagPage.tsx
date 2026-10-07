// PRD 4.4: mobile DAG page -- read-only (2.2), auto-fit zoom, tap node -> bottom sheet,
// sections below the graph for structure stats / rules-and-experience / pending items.
import { useMemo, useState, type CSSProperties } from "react";
import type { GraphNode, WorkflowRecord } from "../api/types";
import { DualDagPanel, type DagTab } from "../components/DualDagPanel";
import { hintForIssue } from "../utils/validationHints";

// Same set as backend task_layer._STEP_NODE_TYPES: nodes carrying expert-described content.
const STEP_NODE_TYPES = new Set(["activity", "approval", "wait", "handoff"]);

const NODE_TYPE_LABEL: Record<string, string> = {
  start: "起点", end: "终点", activity: "活动", wait: "等待",
  decision: "判断", parallel_split: "并行拆分", parallel_join: "并行汇合",
  merge: "汇合", approval: "审批", handoff: "交接",
};

interface Props {
  active: WorkflowRecord | null;
  onBack: () => void;
}

export function MobileDagPage({ active, onBack }: Props) {
  // Which tab the tapped node came from decides how the bottom sheet describes it (a task
  // node is "任务", not "活动", and shows its owner/step count instead of step details).
  const [sheet, setSheet] = useState<{ node: GraphNode; tab: DagTab } | null>(null);
  const sheetNode = sheet?.node ?? null;

  const stats = useMemo(() => {
    if (!active) return null;
    const nodes = active.graph.nodes;
    return {
      total: nodes.length,
      decisions: nodes.filter((n) => n.node_type === "decision").length,
      parallelSplits: nodes.filter((n) => n.node_type === "parallel_split").length,
      approvals: nodes.filter((n) => n.node_type === "approval").length,
      hasRetry: nodes.some((n) => n.retry_semantics?.enabled),
    };
  }, [active]);

  const rules = useMemo(() => {
    if (!active) return [];
    const items: { label: string; detail: string }[] = [];
    for (const e of active.graph.edges) {
      if (e.edge_type === "conditional" && e.condition) {
        items.push({ label: "分支条件", detail: e.condition });
      }
    }
    for (const n of active.graph.nodes) {
      if (n.node_type === "approval" && n.actor_roles.length > 0) {
        items.push({ label: "审批角色", detail: `${n.label}：${n.actor_roles.join("、")}` });
      }
      if (n.retry_semantics?.enabled && n.retry_semantics.description) {
        items.push({ label: "返工说明", detail: n.retry_semantics.description });
      }
    }
    return items;
  }, [active]);

  // Task layer summary for the 任务协作 tab: name / owner / how many SOP steps it covers.
  const taskItems = useMemo(() => {
    const tw = active?.task_workflow;
    if (!active || !tw) return [];
    const stepIds = new Set(active.graph.nodes.filter((n) => STEP_NODE_TYPES.has(n.node_type)).map((n) => n.node_id));
    return tw.tasks.map((t) => {
      const node = tw.graph.nodes.find((n) => n.node_id === t.task_id);
      return {
        id: t.task_id,
        name: node?.label ?? "",
        owner: node?.actor_roles[0] ?? null,
        steps: t.sop_node_ids.filter((id) => stepIds.has(id)).length,
      };
    });
  }, [active]);

  const pendingItems = useMemo(() => {
    if (!active) return [];
    const items: string[] = [];
    if (active.unresolved[0]) items.push(active.unresolved[0].question);
    for (const issue of active.validation) {
      if (issue.level === "error") items.push(hintForIssue(issue));
    }
    return items.slice(0, 5);
  }, [active]);

  const sopSections = (
    <>
      {stats && (
        <section style={sectionStyle}>
          <h4 style={sectionTitle}>结构统计</h4>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <Stat label="步骤总数" value={stats.total} />
            <Stat label="判断点" value={stats.decisions} />
            <Stat label="并行分支" value={stats.parallelSplits} />
            <Stat label="审批节点" value={stats.approvals} />
            {stats.hasRetry && <Stat label="含返工路径" value="是" />}
          </div>
        </section>
      )}

      <section style={sectionStyle}>
        <h4 style={sectionTitle}>规则与经验</h4>
        {rules.length === 0 ? (
          <div style={emptyText}>暂无（分支条件、审批角色或返工说明确定后会显示在这里）</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {rules.map((r, i) => (
              <div key={i} style={{ fontSize: 12.5, color: "#1f2937" }}>
                <span style={{ color: "#2a78d6", fontWeight: 600 }}>{r.label}：</span>
                {r.detail}
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  );

  const taskSection = (
    <section style={sectionStyle}>
      <h4 style={sectionTitle}>任务与负责方</h4>
      {taskItems.length === 0 ? (
        <div style={emptyText}>暂无（步骤讲完后会请你按负责方划分任务）</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {taskItems.map((t, i) => (
            <div key={t.id} style={{ fontSize: 12.5, color: "#1f2937" }}>
              <span style={{ color: "#2a78d6", fontWeight: 600 }}>{i + 1}. {t.name}</span>
              <span style={{ color: "#667085" }}>
                {"　"}{t.owner ? `负责：${t.owner}` : "负责方未说明"} · {t.steps > 0 ? `${t.steps} 个步骤` : "未描述步骤"}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );

  const pendingSection = (
    <section style={sectionStyle}>
      <h4 style={sectionTitle}>待确认信息</h4>
      {pendingItems.length === 0 ? (
        <div style={emptyText}>暂无待确认项</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {pendingItems.map((text, i) => (
            <div key={i} style={{ fontSize: 12.5, color: "#92400e", background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 8, padding: "8px 10px" }}>
              {text}
            </div>
          ))}
        </div>
      )}
    </section>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "#fff" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", borderBottom: "1px solid #e5e7eb" }}>
        <button aria-label="返回会话" onClick={onBack} style={{ border: "none", background: "none", fontSize: 20, padding: 4, minWidth: 44, minHeight: 44 }}>
          ←
        </button>
        <div style={{ fontWeight: 700, fontSize: 14 }}>当前整理出的流程</div>
      </div>

      <div style={{ flex: 1, overflowY: "auto" }}>
        {active ? (
          <DualDagPanel
            active={active}
            readOnly
            scrollable
            onNodeTap={(node, tab) => setSheet({ node, tab })}
            sopEmptyLabel="还没有内容，滑回会话页开始讲述吧。"
            footer={(tab) => (
              <div style={{ padding: "14px", borderTop: "1px solid #e5e7eb" }}>
                {tab === "sop" ? sopSections : taskSection}
                {pendingSection}
              </div>
            )}
          />
        ) : (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 160, color: "#667085", fontSize: 13 }}>
            还没有会话
          </div>
        )}
      </div>

      {sheetNode && (
        <>
          <div onClick={() => setSheet(null)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.35)", zIndex: 20 }} />
          <div style={{ position: "fixed", left: 0, right: 0, bottom: 0, background: "#fff", borderRadius: "16px 16px 0 0", padding: 20, zIndex: 21, boxShadow: "0 -4px 24px rgba(0,0,0,0.15)" }}>
            <div style={{ width: 36, height: 4, background: "#e5e7eb", borderRadius: 2, margin: "0 auto 14px" }} />
            <div style={{ fontSize: 11.5, color: "#2a78d6", fontWeight: 700, marginBottom: 4 }}>
              {sheet?.tab === "task" && sheetNode.node_type === "activity"
                ? "任务"
                : NODE_TYPE_LABEL[sheetNode.node_type] ?? sheetNode.node_type}
            </div>
            <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 10 }}>{sheetNode.label}</div>
            {sheetNode.decision_question && (
              <div style={{ fontSize: 13, color: "#475569", marginBottom: 6 }}>判断问题：{sheetNode.decision_question}</div>
            )}
            {sheetNode.actor_roles.length > 0 && (
              <div style={{ fontSize: 13, color: "#475569", marginBottom: 6 }}>
                {sheet?.tab === "task" ? "负责方" : "涉及角色"}：{sheetNode.actor_roles.join("、")}
              </div>
            )}
            {sheetNode.retry_semantics?.enabled && (
              <div style={{ fontSize: 13, color: "#475569", marginBottom: 6 }}>
                返工说明：{sheetNode.retry_semantics.description ?? "（未记录具体说明）"}
              </div>
            )}
            <div style={{ fontSize: 11.5, color: "#94a3b8", marginTop: 10 }}>
              {sheetNode.expert_confirmed ? "已确认" : `置信度 ${Math.round(sheetNode.confidence * 100)}%（如需修改，请回到会话页说明）`}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div style={{ background: "#f8fafc", borderRadius: 8, padding: "8px 12px", minWidth: 72 }}>
      <div style={{ fontSize: 16, fontWeight: 700, color: "#1f2937" }}>{value}</div>
      <div style={{ fontSize: 11, color: "#667085" }}>{label}</div>
    </div>
  );
}

const sectionStyle: CSSProperties = { marginBottom: 20 };
const sectionTitle: CSSProperties = { fontSize: 12.5, fontWeight: 700, color: "#1f2937", margin: "0 0 8px" };
const emptyText: CSSProperties = { fontSize: 12, color: "#94a3b8" };
