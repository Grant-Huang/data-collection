// PRD 13.5: Dataset Readiness Score (and per-dimension scores) across published versions.
// Single-series line uses the sequential blue per the palette rule established in Phase 3.
import type { TrendPoint } from "../api/client";

export function TrendChart({ points }: { points: TrendPoint[] }) {
  const withScore = points.filter((p) => p.overall !== null) as (TrendPoint & { overall: number })[];
  if (withScore.length < 2) {
    return (
      <div style={{ color: "#94a3b8", fontSize: 12.5 }}>
        至少需要 2 个有效评分（样本量达标）的版本才能画趋势线，当前只有 {withScore.length} 个。
      </div>
    );
  }

  const width = 640;
  const height = 200;
  const padding = 32;
  const xs = withScore.map((_, i) => padding + (i / (withScore.length - 1)) * (width - padding * 2));
  const ys = withScore.map((p) => height - padding - (p.overall / 100) * (height - padding * 2));
  const path = xs.map((x, i) => `${i === 0 ? "M" : "L"}${x},${ys[i]}`).join(" ");

  return (
    <svg width={width} height={height} style={{ maxWidth: "100%" }}>
      {[0, 25, 50, 75, 100].map((v) => {
        const y = height - padding - (v / 100) * (height - padding * 2);
        return (
          <g key={v}>
            <line x1={padding} x2={width - padding} y1={y} y2={y} stroke="#f1f3f5" />
            <text x={4} y={y + 4} fontSize={10} fill="#94a3b8">{v}</text>
          </g>
        );
      })}
      <path d={path} fill="none" stroke="#2a78d6" strokeWidth={2} />
      {xs.map((x, i) => (
        <g key={i}>
          <circle cx={x} cy={ys[i]} r={3.5} fill="#2a78d6" />
          <text x={x} y={height - 8} fontSize={10} fill="#667085" textAnchor="middle">v{withScore[i].version_number}</text>
          <text x={x} y={ys[i] - 8} fontSize={10} fill="#1f2937" textAnchor="middle" fontWeight={700}>{withScore[i].overall}</text>
        </g>
      ))}
    </svg>
  );
}
