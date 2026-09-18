// A thin drag bar between desktop panels: drag to resize, click the chevron to collapse the
// panel on the given side entirely. Used by SessionPage for the history and DAG side panels.
import { useCallback, useRef } from "react";

interface Props {
  onResize: (deltaPx: number) => void;
  onToggleCollapse: () => void;
  collapsed: boolean;
  // Which side of the handle the collapsible panel sits on -- flips the chevron direction.
  panelSide: "left" | "right";
}

export function ResizeHandle({ onResize, onToggleCollapse, collapsed, panelSide }: Props) {
  const dragStartX = useRef<number | null>(null);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (collapsed) return;
      dragStartX.current = e.clientX;
      const onMove = (moveEvent: MouseEvent) => {
        if (dragStartX.current === null) return;
        const delta = moveEvent.clientX - dragStartX.current;
        dragStartX.current = moveEvent.clientX;
        onResize(delta);
      };
      const onUp = () => {
        dragStartX.current = null;
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [collapsed, onResize],
  );

  // collapsed chevron points toward where the panel would reappear from; expanded chevron
  // points toward collapsing it (i.e. toward the panel it controls).
  const chevron = panelSide === "left" ? (collapsed ? "›" : "‹") : collapsed ? "‹" : "›";

  return (
    <div
      onMouseDown={onMouseDown}
      style={{
        width: 10,
        flexShrink: 0,
        cursor: collapsed ? "default" : "col-resize",
        position: "relative",
        background: "transparent",
      }}
    >
      <div style={{ position: "absolute", left: 4, top: 0, bottom: 0, width: 1, background: "#e5e7eb" }} />
      <button
        aria-label={collapsed ? "展开面板" : "收起面板"}
        onClick={(e) => {
          e.stopPropagation();
          onToggleCollapse();
        }}
        onMouseDown={(e) => e.stopPropagation()}
        style={{
          position: "absolute",
          top: "50%",
          left: -1,
          transform: "translateY(-50%)",
          width: 14,
          height: 36,
          borderRadius: 6,
          border: "1px solid #e5e7eb",
          background: "#fff",
          color: "#94a3b8",
          fontSize: 11,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 2,
        }}
      >
        {chevron}
      </button>
    </div>
  );
}
