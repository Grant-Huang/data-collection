// PRD 13.2: every top-level metric needs a tips icon explaining what it measures. Click to
// toggle (works without hover, so it's usable on touch too) with a small popover.
import { useState } from "react";

export function TipIcon({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span style={{ position: "relative", display: "inline-block", marginLeft: 4 }}>
      <button
        aria-label="说明"
        onClick={() => setOpen((v) => !v)}
        onBlur={() => setOpen(false)}
        style={{
          width: 14, height: 14, borderRadius: "50%", border: "1px solid #94a3b8", background: "#fff",
          color: "#94a3b8", fontSize: 10, lineHeight: "12px", padding: 0, cursor: "pointer",
        }}
      >
        i
      </button>
      {open && (
        <div
          style={{
            position: "absolute", top: 20, left: 0, zIndex: 30, width: 240,
            background: "#1f2937", color: "#fff", fontSize: 11.5, lineHeight: 1.5,
            borderRadius: 8, padding: "8px 10px", boxShadow: "0 4px 16px rgba(0,0,0,0.2)",
          }}
        >
          {text}
        </div>
      )}
    </span>
  );
}
