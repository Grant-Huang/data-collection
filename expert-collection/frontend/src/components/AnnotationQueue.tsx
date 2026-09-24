// Annotation work queue on the Dashboard (IMPLEMENTATION_PLAN.md section 15). Replaces the flat
// "every record + 去标注" list with:
// - filters by stage, defaulting to "我可处理" (what *this* annotator can act on right now,
//   decided from the round's participant names before any work is done);
// - progress (records done / total) and settled-outcome stats incl. structured reason tags;
// - optional ordering by machine signals so the likeliest-problematic records come first;
// - opening a record freezes the current filtered list as the panel's queue, so
//   "提交并下一条" / ←→ walk a stable sequence even as statuses change underneath.
// Only settled outcomes are shown per record -- an in-progress verdict here would leak into
// the next independent annotator's view (the blind-review flaw this replaces).
import { useMemo, useState } from "react";
import type { AnnotationStage, AnnotationSummary, PriorRecordSummary, ReasonTag, Role, SourceType } from "../api/types";
import { GOLD_STATUS_LABELS, REASON_TAG_LABELS, STAGE_LABELS, VERDICT_LABELS } from "../api/types";
import { useAnnotatorName } from "../hooks/useAnnotatorName";
import { accessFor } from "../utils/annotationAccess";
import { PriorAnnotationPanel } from "./PriorAnnotationPanel";

type Filter = "mine" | "all" | AnnotationStage;
type Sort = "default" | "signals";

const STAGE_ORDER: AnnotationStage[] = ["first_review", "second_review", "arbitration", "rework", "done"];
const STAGE_COLOR: Record<AnnotationStage, { bg: string; fg: string }> = {
  first_review: { bg: "#f1f5f9", fg: "#667085" },
  second_review: { bg: "#eef4fc", fg: "#2a78d6" },
  arbitration: { bg: "#fff7ed", fg: "#c2410c" },
  rework: { bg: "#f5f3ff", fg: "#7c3aed" },
  done: { bg: "#eafaea", fg: "#0ca30c" },
};

export function AnnotationQueue({
  sourceType, versionId, records, summary, role, onChanged,
}: {
  sourceType: SourceType;
  versionId: string;
  records: PriorRecordSummary[];
  summary: AnnotationSummary | null;
  role: Role;
  onChanged: () => void;
}) {
  const { annotatorName, setAnnotatorName } = useAnnotatorName();
  const [filter, setFilter] = useState<Filter>("mine");
  const [sort, setSort] = useState<Sort>("default");
  const [openId, setOpenId] = useState<string | null>(null);
  const [queue, setQueue] = useState<string[]>([]);

  const matches = (r: PriorRecordSummary, f: Filter) =>
    f === "all" ? true : f === "mine" ? r.stage !== "done" && accessFor(r, annotatorName).canAct : r.stage === f;

  const visible = useMemo(() => {
    const list = records.filter((r) => matches(r, filter));
    if (sort === "signals") {
      list.sort((a, b) => b.signal_error_count - a.signal_error_count || b.signal_warning_count - a.signal_warning_count);
    }
    return list;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [records, filter, sort, annotatorName]);

  const doneCount = records.filter((r) => r.stage === "done").length;
  const filters: { key: Filter; label: string }[] = [
    { key: "mine", label: "我可处理" },
    { key: "all", label: "全部" },
    ...STAGE_ORDER.map((s) => ({ key: s as Filter, label: STAGE_LABELS[s] })),
  ];

  function open(recordId: string) {
    setQueue(visible.map((r) => r.record_id));
    setOpenId(recordId);
  }

  const topReasons = summary
    ? (Object.entries(summary.reason_tag_counts) as [ReasonTag, number][]).sort((a, b) => b[1] - a[1]).slice(0, 4)
    : [];

  return (
    <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20, marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10, gap: 12, flexWrap: "wrap" }}>
        <div style={{ fontSize: 13, fontWeight: 700 }}>
          {sourceType === "public_extracted" ? "Prior / Gold 标注（双人独立盲标 → 分歧仲裁 → 需要修改则返工）" : "专家复核（双人独立盲标 → 分歧仲裁 → 需要修改则返工 → Gold）"}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 12, color: "#667085" }}>我是</span>
          <input
            value={annotatorName}
            onChange={(e) => setAnnotatorName(e.target.value)}
            placeholder="标注人姓名（会记住）"
            style={{ width: 150, border: `1px solid ${annotatorName.trim() ? "#d0d5dd" : "#f59e0b"}`, borderRadius: 6, padding: "4px 8px", fontSize: 12 }}
          />
        </div>
      </div>

      {/* Progress + settled stats */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ height: 6, background: "#f1f5f9", borderRadius: 999, overflow: "hidden", marginBottom: 6 }}>
          <div style={{ width: `${records.length ? (doneCount / records.length) * 100 : 0}%`, height: "100%", background: "#0ca30c" }} />
        </div>
        <div style={{ fontSize: 11.5, color: "#94a3b8" }}>
          已完成 {doneCount}/{records.length}
          {summary && (
            <>
              {" ・ "}Gold {summary.gold_counts.gold ?? 0} 条
              {(["accepted", "needs_revision", "rejected"] as const).some((v) => summary.verdict_counts[v]) && (
                <>
                  {" ・ 已定结论："}
                  {(["accepted", "needs_revision", "rejected"] as const)
                    .filter((v) => summary.verdict_counts[v])
                    .map((v) => `${VERDICT_LABELS[v]} ${summary.verdict_counts[v]}`)
                    .join("，")}
                </>
              )}
              {summary.rework_count > 0 && ` ・ 返工 ${summary.rework_count} 次`}
              {summary.agreement_kappa !== null && ` ・ 一致性 κ=${summary.agreement_kappa}`}
              {topReasons.length > 0 && ` ・ 主要问题：${topReasons.map(([t, n]) => `${REASON_TAG_LABELS[t]} ${n}`).join("，")}`}
            </>
          )}
        </div>
      </div>

      {/* Filters + sort */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          {filters.map((f) => {
            const count = records.filter((r) => matches(r, f.key)).length;
            const active = filter === f.key;
            return (
              <button
                key={f.key}
                onClick={() => setFilter(f.key)}
                style={{
                  border: `1px solid ${active ? "#2a78d6" : "#e5e7eb"}`, background: active ? "#eef4fc" : "#fff",
                  color: active ? "#2a78d6" : "#475569", borderRadius: 999, padding: "3px 12px", fontSize: 12, cursor: "pointer",
                }}
              >
                {f.label} {count}
              </button>
            );
          })}
        </div>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as Sort)}
          style={{ border: "1px solid #d0d5dd", borderRadius: 6, padding: "3px 6px", fontSize: 12, color: "#475569" }}
        >
          <option value="default">默认顺序</option>
          <option value="signals">机器信号多的优先</option>
        </select>
      </div>

      {visible.length > 0 && filter !== "done" && (
        <div style={{ marginBottom: 6 }}>
          <button
            onClick={() => open(visible[0].record_id)}
            style={{ border: "none", background: "#2a78d6", color: "#fff", borderRadius: 6, padding: "5px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
          >
            从第一条开始连续处理（{visible.length} 条）
          </button>
        </div>
      )}

      <div>
        {visible.length === 0 && (
          <div style={{ fontSize: 12.5, color: "#94a3b8", padding: "16px 0", textAlign: "center" }}>
            {filter === "mine" ? "当前没有你可以处理的记录（已标过的记录需要换人复核 / 仲裁）。" : "没有符合条件的记录。"}
          </div>
        )}
        {visible.map((r) => {
          const acc = accessFor(r, annotatorName);
          const color = STAGE_COLOR[r.stage];
          return (
            <div key={r.record_id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #f1f3f5", gap: 8 }}>
              <div style={{ fontSize: 12.5, minWidth: 0 }}>
                {r.name} <span style={{ color: "#94a3b8" }}>（{r.node_count} 节点{r.round > 1 ? `・第 ${r.round} 轮` : ""}）</span>
                {(r.signal_error_count > 0 || r.signal_warning_count > 0) && (
                  <span
                    title="机器预检信号：结构校验 / 近重复 / 疑似微工作流复用，打开记录可查看详情"
                    style={{ marginLeft: 6, fontSize: 11, color: r.signal_error_count ? "#991b1b" : "#92400e" }}
                  >
                    {r.signal_error_count ? "✖" : "⚠"} {r.signal_error_count + r.signal_warning_count}
                  </span>
                )}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                <span style={{ fontSize: 11, fontWeight: 600, borderRadius: 999, padding: "2px 10px", background: color.bg, color: color.fg }}>
                  {STAGE_LABELS[r.stage]}
                  {r.final_verdict && `・${VERDICT_LABELS[r.final_verdict]}`}
                </span>
                {r.gold_status === "gold" && (
                  <span style={{ fontSize: 11, fontWeight: 600, borderRadius: 999, padding: "2px 10px", background: "#fff7e6", color: "#b45309" }}>
                    {GOLD_STATUS_LABELS.gold}
                  </span>
                )}
                <button
                  onClick={() => open(r.record_id)}
                  title={acc.reason ?? undefined}
                  style={{
                    border: `1px solid ${acc.canAct ? "#2a78d6" : "#d0d5dd"}`, color: acc.canAct ? "#2a78d6" : "#667085",
                    background: "#fff", borderRadius: 6, padding: "4px 12px", fontSize: 11.5, cursor: "pointer", minWidth: 64,
                  }}
                >
                  {acc.actionLabel}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {openId && (
        <PriorAnnotationPanel
          versionId={versionId}
          recordId={openId}
          role={role}
          queue={queue}
          annotatorName={annotatorName}
          setAnnotatorName={setAnnotatorName}
          onClose={() => setOpenId(null)}
          onSaved={onChanged}
          onNavigate={setOpenId}
        />
      )}
    </div>
  );
}
