// PRD 13.3/13.5: one dimension row -- bar length uses a single sequential blue (magnitude),
// the good/warning/poor badge uses fixed status colors, never the bar's own blue (13.5's
// "两者不混用" rule). Click the row to open the explanation modal (13.3.1).
import { useState } from "react";
import { api } from "../api/client";
import type { DimensionScore, ScoreBand } from "../api/types";

const BAND_STYLE: Record<ScoreBand, { color: string; label: string }> = {
  good: { color: "#0ca30c", label: "良好" },
  warning: { color: "#fab219", label: "待改善" },
  poor: { color: "#ec835a", label: "较差" },
  insufficient_sample: { color: "#94a3b8", label: "样本不足" },
};

interface Props {
  dimensionKey: string;
  label: string;
  weight: number;
  dim: DimensionScore;
  versionId?: string;
}

export function ScoreBar({ dimensionKey, label, weight, dim, versionId }: Props) {
  const [open, setOpen] = useState(false);
  const [problems, setProblems] = useState<{ record_id: string; name: string; reason: string }[] | null>(null);
  const [loadingProblems, setLoadingProblems] = useState(false);
  const band = BAND_STYLE[dim.band];
  const pct = dim.score ?? 0;

  async function handleDrillDown() {
    if (!versionId) return;
    setLoadingProblems(true);
    try {
      const res = await api.drillDown(versionId, dimensionKey);
      setProblems(res.problem_records);
    } finally {
      setLoadingProblems(false);
    }
  }

  return (
    <>
      <div
        onClick={() => setOpen(true)}
        style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", cursor: "pointer", borderBottom: "1px solid #f1f3f5" }}
      >
        <div style={{ width: 150, flexShrink: 0, fontSize: 12.5, color: "#1f2937" }}>
          {label} <span style={{ color: "#94a3b8", fontSize: 11 }}>({Math.round(weight * 100)}%)</span>
        </div>
        <div style={{ flex: 1, height: 8, background: "#eef1f4", borderRadius: 4, overflow: "hidden" }}>
          <div style={{ width: `${pct}%`, height: "100%", background: "#2a78d6", borderRadius: 4 }} />
        </div>
        <div style={{ width: 44, textAlign: "right", fontSize: 13, fontWeight: 700, color: "#1f2937" }}>
          {dim.score ?? "--"}
        </div>
        <div
          style={{
            width: 66, textAlign: "center", fontSize: 11, fontWeight: 600, borderRadius: 999,
            padding: "3px 0", background: `${band.color}1a`, color: band.color,
          }}
        >
          {band.label}
        </div>
      </div>

      {open && (
        <>
          <div onClick={() => setOpen(false)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.35)", zIndex: 40 }} />
          <div
            style={{
              position: "fixed", top: "50%", left: "50%", transform: "translate(-50%, -50%)", zIndex: 41,
              width: 480, maxWidth: "90vw", maxHeight: "80vh", overflowY: "auto",
              background: "#fff", borderRadius: 12, padding: 24, boxShadow: "0 12px 40px rgba(0,0,0,0.25)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <div style={{ fontSize: 16, fontWeight: 700 }}>{label}</div>
                <div style={{ fontSize: 22, fontWeight: 800, color: band.color, marginTop: 4 }}>
                  {dim.score ?? "--"} <span style={{ fontSize: 12, fontWeight: 600 }}>{band.label}</span>
                </div>
              </div>
              <button onClick={() => setOpen(false)} style={{ border: "none", background: "none", fontSize: 18, cursor: "pointer" }}>
                ✕
              </button>
            </div>

            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#667085", marginBottom: 6 }}>评分标准</div>
              <div style={{ fontSize: 13, color: "#374151", lineHeight: 1.6 }}>{dim.scope_note}</div>
            </div>

            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#667085", marginBottom: 6 }}>当前分数的依据</div>
              <div style={{ fontSize: 13, color: "#1f2937", lineHeight: 1.7, background: "#f8fafc", borderRadius: 8, padding: "10px 12px" }}>
                {dim.explanation}
              </div>
            </div>

            {versionId && dim.score !== null && (
              <div style={{ marginTop: 16 }}>
                {problems === null ? (
                  <button
                    onClick={handleDrillDown}
                    disabled={loadingProblems}
                    style={{ border: "1px solid #2a78d6", color: "#2a78d6", background: "#fff", borderRadius: 6, padding: "6px 12px", fontSize: 12, cursor: "pointer" }}
                  >
                    {loadingProblems ? "定位中…" : "定位问题样本"}
                  </button>
                ) : (
                  <>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "#667085", marginBottom: 6 }}>
                      问题样本（{problems.length}）
                    </div>
                    {problems.length === 0 ? (
                      <div style={{ fontSize: 12.5, color: "#94a3b8" }}>没有找到明显拖低本维度分数的具体记录。</div>
                    ) : (
                      <div style={{ maxHeight: 180, overflowY: "auto" }}>
                        {problems.map((p) => (
                          <div key={p.record_id} style={{ fontSize: 12, padding: "6px 0", borderBottom: "1px solid #f1f3f5" }}>
                            <span style={{ fontWeight: 600 }}>{p.name}</span>
                            <span style={{ color: "#94a3b8" }}> — {p.reason}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </>
  );
}
