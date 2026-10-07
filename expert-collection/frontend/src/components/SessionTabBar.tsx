// Tab strip + search box for the session list (shared by the desktop rail and the mobile sheet).
import { SESSION_TABS, type SessionTab } from "../utils/sessionTabs";

interface Props {
  tab: SessionTab;
  onTab: (tab: SessionTab) => void;
  counts: Record<SessionTab, number>;
  query: string;
  onQuery: (q: string) => void;
  // Mobile wants bigger touch targets (PRD 5.3: >= 44px).
  touch?: boolean;
}

export function SessionTabBar({ tab, onTab, counts, query, onQuery, touch }: Props) {
  return (
    <div>
      <div role="tablist" aria-label="会话分类" style={{ display: "flex", borderBottom: "1px solid #e5e7eb" }}>
        {SESSION_TABS.map((t) => {
          const on = tab === t.key;
          return (
            <button
              key={t.key}
              role="tab"
              aria-selected={on}
              onClick={() => onTab(t.key)}
              style={{
                flex: 1, border: "none", background: "none", cursor: "pointer", whiteSpace: "nowrap",
                padding: touch ? "12px 2px" : "8px 2px", minHeight: touch ? 44 : undefined, fontSize: 12,
                color: on ? "#2a78d6" : "#667085", fontWeight: on ? 700 : 500,
                borderBottom: `2px solid ${on ? "#2a78d6" : "transparent"}`,
              }}
            >
              {t.label}
              {counts[t.key] > 0 && <span style={{ marginLeft: 3, fontSize: 10.5, opacity: 0.8 }}>{counts[t.key]}</span>}
            </button>
          );
        })}
      </div>
      <div style={{ padding: touch ? "10px 16px" : "8px 12px" }}>
        <input
          type="search"
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          placeholder="搜索会话名称"
          aria-label="搜索会话"
          style={{
            width: "100%", boxSizing: "border-box", border: "1px solid #d0d5dd", borderRadius: 6,
            padding: touch ? "10px 10px" : "6px 8px", fontSize: touch ? 14 : 12, color: "#1f2937",
          }}
        />
      </div>
    </div>
  );
}
