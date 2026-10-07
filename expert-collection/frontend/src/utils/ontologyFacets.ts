// Short, human-readable tags for the ontology dimensions captured on a step (design doc
// docs/expert-workflow-collection/ontology/MANUFACTURING_OPERATIONAL_ONTOLOGY.md): the
// threshold / expected value of a decision step, the time limit and escalation target of an
// approval step. Shown under the node label in DagView; the full verbatim answers go in the
// hover tooltip.
import type { EvaluationCriterion, GraphNode, LimitBand, SlaConfig } from "../api/types";

const ISO_UNITS: [RegExp, string][] = [
  [/(\d+)W/, "周"],
  [/(\d+)D/, "天"],
  [/T.*?(\d+)H/, "小时"],
  [/T.*?(\d+)M/, "分钟"],
];

/** "PT4H" -> "4小时", "P3D" -> "3天", "PT90M" -> "90分钟". Unknown shapes are returned as-is. */
export function formatIsoDuration(iso: string): string {
  const parts = ISO_UNITS.map(([re, unit]) => {
    const m = iso.match(re);
    return m ? `${m[1]}${unit}` : "";
  }).filter(Boolean);
  return parts.length ? parts.join("") : iso;
}

function formatBand(b: LimitBand, unit: string): string {
  if (b.lower != null && b.upper != null) return `${b.lower}–${b.upper}${unit}`;
  if (b.lower != null) return `${b.lower_inclusive === false ? ">" : "≥"}${b.lower}${unit}`;
  if (b.upper != null) return `${b.upper_inclusive === false ? "<" : "≤"}${b.upper}${unit}`;
  return "";
}

function criterionFacet(c: EvaluationCriterion): string {
  const unit = c.unit ?? "";
  const normal = (c.limits ?? []).find((b) => b.band === "normal");
  const reject = (c.limits ?? []).find((b) => b.band === "reject");
  if (normal) return `正常 ${formatBand(normal, unit)}`;
  if (reject) return `不合格 ${formatBand(reject, unit)}`;
  if (c.expected?.target != null) return `目标 ${c.expected.target}${unit}`;
  return "有判断标准";
}

function slaFacets(sla: SlaConfig): string[] {
  const out = [sla.duration ? `时限 ${formatIsoDuration(sla.duration)}` : "有时限要求"];
  if (sla.violation_action === "escalate" && sla.escalate_to_role) out.push(`超时找${sla.escalate_to_role}`);
  return out;
}

export function ontologyFacets(node: GraphNode): string[] {
  const facets = (node.evaluation_criteria ?? []).slice(0, 1).map(criterionFacet);
  if (node.sla_config) facets.push(...slaFacets(node.sla_config));
  return facets;
}

/** Tooltip lines: the expert's own words behind each captured dimension. */
export function ontologyTooltip(node: GraphNode): string[] {
  const lines: string[] = [];
  for (const c of node.evaluation_criteria ?? []) {
    const extra = c.expected?.target != null ? `（正常 ${c.expected.target}${c.unit ?? ""}）` : "";
    if (c.description) lines.push(`判断标准：「${c.description}」${extra}`);
  }
  const sla = node.sla_config;
  if (sla?.description) lines.push(`时限：「${sla.description}」`);
  if (sla?.violation_action === "escalate" && sla.escalate_to_role) lines.push(`超时升级给：${sla.escalate_to_role}`);
  if (sla?.violation_action === "none") lines.push("超时无人跟进");
  return lines;
}
