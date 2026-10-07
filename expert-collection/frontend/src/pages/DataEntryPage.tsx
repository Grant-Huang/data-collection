// 顶部导航「数据录入与标注」-- 合并了原来独立的「专家采集」页和原来嵌在 Dashboard 里的标注
// 功能，下面两个 tab：
// - 专家录入：原样复用 SessionPage（三栏会话式采集，逻辑完全没变）
// - 数据标注：从 Dashboard 挪过来的 Prior/专家复核标注入口（见 AnnotationTab.tsx）
import { useState } from "react";
import type { Role } from "../api/types";
import { SessionPage } from "./SessionPage";
import { AnnotationTab } from "./AnnotationTab";

type Tab = "entry" | "annotation";

const TABS: { key: Tab; label: string }[] = [
  { key: "entry", label: "专家录入" },
  { key: "annotation", label: "数据标注" },
];

export function DataEntryPage({ role }: { role: Role }) {
  const [tab, setTab] = useState<Tab>("entry");

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", gap: 4, borderBottom: "1px solid #e5e7eb", padding: "0 16px", flexShrink: 0 }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              border: "none", background: "none", padding: "9px 14px", fontSize: 12.5, cursor: "pointer",
              color: tab === t.key ? "#2a78d6" : "#667085", fontWeight: tab === t.key ? 700 : 500,
              borderBottom: tab === t.key ? "2px solid #2a78d6" : "2px solid transparent",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        {tab === "entry" && <SessionPage />}
        {tab === "annotation" && <AnnotationTab role={role} />}
      </div>
    </div>
  );
}
