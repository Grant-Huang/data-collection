// Small shared tab-button rows so nested-tab pages (数据与实验管理 / 系统管理) don't each
// hand-roll the same style object. UnderlineTabs is for a page's top-level section switcher;
// PillTabs is for a subtab row nested inside one of those sections.
import type { CSSProperties } from "react";

export interface TabItem<T extends string> {
  key: T;
  label: string;
}

export function UnderlineTabs<T extends string>({ tabs, active, onChange }: { tabs: TabItem<T>[]; active: T; onChange: (key: T) => void }) {
  return (
    <div style={{ display: "flex", gap: 4, borderBottom: "1px solid #e5e7eb", marginBottom: 16 }}>
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          style={{
            border: "none", background: "none", padding: "8px 14px", fontSize: 13, cursor: "pointer",
            color: active === t.key ? "#2a78d6" : "#667085", fontWeight: active === t.key ? 700 : 500,
            borderBottom: active === t.key ? "2px solid #2a78d6" : "2px solid transparent",
          }}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function PillTabs<T extends string>({ tabs, active, onChange }: { tabs: TabItem<T>[]; active: T; onChange: (key: T) => void }) {
  const style: CSSProperties = { display: "flex", border: "1px solid #d0d5dd", borderRadius: 999, overflow: "hidden", fontSize: 12, width: "fit-content" };
  return (
    <div style={style}>
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          style={{
            border: "none", padding: "5px 12px", cursor: "pointer",
            background: active === t.key ? "#2a78d6" : "#fff",
            color: active === t.key ? "#fff" : "#475569", fontWeight: 600,
          }}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
