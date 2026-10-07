// 「还差什么」(B6): the clarification list the interview works through, as a dozen plain-language
// items -- settled / being asked now / still to ask / not asked because the interview stopped.
// Collapsed it is one line ("还差 3 项：…"), so it never pushes the conversation down; expanded
// it is the whole list. Shared by the desktop header and the mobile progress panel.
import { useState } from "react";
import type { ChecklistItem } from "../api/types";

const MARK: Record<ChecklistItem["status"], { icon: string; color: string; note?: string }> = {
  done: { icon: "✓", color: "#0ca30c" },
  asking: { icon: "●", color: "#2a78d6", note: "正在问" },
  open: { icon: "○", color: "#94a3b8" },
  skipped: { icon: "–", color: "#b45309", note: "没问到，确认前可以直接补充" },
};

interface Props {
  items: ChecklistItem[];
  // Mobile shows the list already expanded inside its own panel.
  defaultOpen?: boolean;
}

export function CompletenessChecklist({ items, defaultOpen = false }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const left = items.filter((i) => i.status !== "done");
  const summary = left.length === 0 ? "该问的都问到了" : `还差 ${left.length} 项：${left.map((i) => i.label).join("、")}`;

  return (
    <div className="checklist">
      <button type="button" className="checklist-summary" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="checklist-summary-text">{summary}</span>
        <span className="checklist-toggle">{open ? "收起" : "查看清单"}</span>
      </button>
      {open && (
        <ul className="checklist-items" aria-label="完整性清单">
          {items.map((i) => {
            const m = MARK[i.status];
            return (
              <li key={i.key} className={`checklist-item ${i.status}`}>
                <span aria-hidden style={{ color: m.color, width: 14, display: "inline-block", textAlign: "center" }}>{m.icon}</span>
                <span>{i.label}</span>
                {m.note && <span className="checklist-note" style={{ color: m.color }}>{m.note}</span>}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
