// Shared bubble rendering between desktop ChatPanel and the mobile chat page, so message
// styling stays identical across both views per PRD 4.3 ("与桌面端消息样式一致").
import type { ConversationTurn } from "../api/types";

export function MessageList({ turns }: { turns: ConversationTurn[] }) {
  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "16px", display: "flex", flexDirection: "column", gap: 12 }}>
      {turns.map((t) => (
        <div
          key={t.turn_id}
          style={{
            alignSelf: t.role === "expert" ? "flex-end" : "flex-start",
            maxWidth: "82%",
            background: t.role === "expert" ? "#2a78d6" : "#f1f3f5",
            color: t.role === "expert" ? "#fff" : "#1f2937",
            borderRadius: 12,
            padding: "8px 12px",
            fontSize: 13.5,
            lineHeight: 1.5,
            whiteSpace: "pre-wrap",
          }}
        >
          {t.text}
        </div>
      ))}
    </div>
  );
}
