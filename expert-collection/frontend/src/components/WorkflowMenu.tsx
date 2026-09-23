// 左栏会话清单每一行右侧的「...」下拉菜单 -- 置顶/取消置顶、重命名、归档/取消归档，其他
// 功能（比如未来要加的）都挂在这一个菜单里，不用再往行内塞更多按钮。
import { useEffect, useRef, useState } from "react";
import type { WorkflowSummary } from "../api/types";

interface Props {
  workflow: WorkflowSummary;
  onRename: (name: string) => void;
  onTogglePin: () => void;
  onToggleArchive: () => void;
}

export function WorkflowMenu({ workflow, onRename, onTogglePin, onToggleArchive }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClickAway = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClickAway);
    return () => document.removeEventListener("mousedown", onClickAway);
  }, [open]);

  const item = (label: string, onClick: () => void, danger = false): JSX.Element => (
    <button
      onClick={(e) => {
        e.stopPropagation();
        setOpen(false);
        onClick();
      }}
      style={{
        display: "block", width: "100%", textAlign: "left", border: "none", background: "none",
        padding: "8px 12px", fontSize: 12.5, color: danger ? "#b42318" : "#1f2937", cursor: "pointer",
      }}
    >
      {label}
    </button>
  );

  return (
    <div ref={ref} style={{ position: "relative" }} onClick={(e) => e.stopPropagation()}>
      <button
        aria-label="更多操作"
        onClick={() => setOpen((v) => !v)}
        style={{
          border: "none", background: "none", cursor: "pointer", fontSize: 14, color: "#98a2b3",
          padding: "2px 6px", borderRadius: 4, lineHeight: 1,
        }}
      >
        ⋯
      </button>
      {open && (
        <div
          style={{
            position: "absolute", right: 0, top: "100%", zIndex: 20, minWidth: 132,
            background: "#fff", border: "1px solid #e5e7eb", borderRadius: 8,
            boxShadow: "0 4px 16px rgba(0,0,0,0.12)", overflow: "hidden", marginTop: 4,
          }}
        >
          {item(workflow.pinned ? "取消置顶" : "置顶", onTogglePin)}
          {item("重命名", () => {
            const next = window.prompt("重命名会话", workflow.name);
            if (next !== null && next.trim()) onRename(next.trim());
          })}
          {item(workflow.archived ? "取消归档" : "归档", onToggleArchive, !workflow.archived)}
        </div>
      )}
    </div>
  );
}
