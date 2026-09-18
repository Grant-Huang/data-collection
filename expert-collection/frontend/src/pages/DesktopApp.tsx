// Desktop-only shell with a slim top nav between the collection session and the Dashboard
// (PRD 13: Dashboard is desktop-only, and per 1.4 desktop carries every module).
import { useState } from "react";
import { SessionPage } from "./SessionPage";
import { DashboardPage } from "./DashboardPage";

type View = "session" | "dashboard";

export function DesktopApp() {
  const [view, setView] = useState<View>("session");

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 4, padding: "0 12px", height: 40, borderBottom: "1px solid #e5e7eb", flexShrink: 0, fontFamily: "-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif" }}>
        {([
          ["session", "专家采集"],
          ["dashboard", "Dashboard"],
        ] as [View, string][]).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setView(key)}
            style={{
              border: "none", background: "none", padding: "8px 12px", fontSize: 12.5, cursor: "pointer",
              color: view === key ? "#2a78d6" : "#667085", fontWeight: view === key ? 700 : 500,
              borderBottom: view === key ? "2px solid #2a78d6" : "2px solid transparent",
            }}
          >
            {label}
          </button>
        ))}
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        {view === "session" ? <SessionPage /> : <DashboardPage />}
      </div>
    </div>
  );
}
