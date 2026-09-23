// Desktop-only shell: top nav between the collection session and the other modules, gated by
// role per PRD 16.2 (expert sees only 专家采集; researcher adds Dashboard/实验中心; admin adds
// 数据与实验管理/系统管理) -- plus the role switcher itself, which has to stay visible to
// everyone so you can switch identity (IMPLEMENTATION_PLAN.md assumption 1's simplest
// current-identity selector, finally wired up this phase).
import { useState } from "react";
import { useRole } from "../hooks/useRole";
import { ROLE_LABELS } from "../api/types";
import type { Role } from "../api/types";
import { SessionPage } from "./SessionPage";
import { DashboardPage } from "./DashboardPage";
import { ExperimentCenterPage } from "./ExperimentCenterPage";
import { DataExperimentManagementPage } from "./DataExperimentManagementPage";
import { SystemManagementPage } from "./SystemManagementPage";

type View = "session" | "dashboard" | "experiments" | "data-experiment-admin" | "system-admin";

const NAV: { key: View; label: string; minRole: Role[] }[] = [
  { key: "session", label: "专家采集", minRole: ["expert", "researcher", "admin"] },
  { key: "dashboard", label: "Dashboard", minRole: ["researcher", "admin"] },
  { key: "experiments", label: "实验中心", minRole: ["researcher", "admin"] },
  { key: "data-experiment-admin", label: "数据与实验管理", minRole: ["admin"] },
  { key: "system-admin", label: "系统管理", minRole: ["admin"] },
];

export function DesktopApp() {
  const { role, setRole } = useRole();
  const [view, setView] = useState<View>("session");

  const visibleNav = NAV.filter((n) => n.minRole.includes(role));
  const activeView = visibleNav.some((n) => n.key === view) ? view : "session";

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 12px", height: 40, borderBottom: "1px solid #e5e7eb", flexShrink: 0, fontFamily: "-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          {visibleNav.map((n) => (
            <button
              key={n.key}
              onClick={() => setView(n.key)}
              style={{
                border: "none", background: "none", padding: "8px 12px", fontSize: 12.5, cursor: "pointer",
                color: activeView === n.key ? "#2a78d6" : "#667085", fontWeight: activeView === n.key ? 700 : 500,
                borderBottom: activeView === n.key ? "2px solid #2a78d6" : "2px solid transparent",
              }}
            >
              {n.label}
            </button>
          ))}
        </div>
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as Role)}
          title="当前身份（无真实登录系统，仅用于演示角色权限）"
          style={{ border: "1px solid #d0d5dd", borderRadius: 6, padding: "4px 8px", fontSize: 11.5, color: "#475569" }}
        >
          {(Object.keys(ROLE_LABELS) as Role[]).map((r) => (
            <option key={r} value={r}>{ROLE_LABELS[r]}</option>
          ))}
        </select>
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        {activeView === "session" && <SessionPage />}
        {activeView === "dashboard" && <DashboardPage role={role} />}
        {activeView === "experiments" && <ExperimentCenterPage role={role} />}
        {activeView === "data-experiment-admin" && <DataExperimentManagementPage />}
        {activeView === "system-admin" && <SystemManagementPage />}
      </div>
    </div>
  );
}
