// PRD 5.1/5.4: mobile app shell -- session page (home, static) and a read-only DAG page that
// slides in as a card from the right on a right-swipe, and slides back out on a left-swipe.
// The left 20px is excluded on the session page only, reserving it for the browser's own
// edge-triggered back gesture; the DAG page's return swipe isn't edge-triggered so it has no
// such exclusion. Voice recording temporarily disables the gesture (PRD 5.4).
import { useRef, useState } from "react";
import { useWorkflowSession } from "../hooks/useWorkflowSession";
import { MobileChatPage } from "./MobileChatPage";
import { MobileDagPage } from "./MobileDagPage";
import { HistorySheet } from "./HistorySheet";

const EDGE_EXCLUSION_PX = 20;
const SWIPE_THRESHOLD_PX = 70;

type Page = "chat" | "dag";

export function MobileApp() {
  const { workflows, active, sending, creating, error, selectWorkflow, createWorkflow, sendTurn, confirmWorkflow } =
    useWorkflowSession();

  const [page, setPage] = useState<Page>("chat");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [progressOpen, setProgressOpen] = useState(false);
  const [recording, setRecording] = useState(false);
  // Drag progress in [0, 1]: 0 = DAG page fully hidden (off right edge), 1 = fully shown.
  const [dragProgress, setDragProgress] = useState<number | null>(null);

  const touchStart = useRef<{ x: number; y: number; blockedByEdge: boolean; width: number } | null>(null);

  function onTouchStart(e: React.TouchEvent) {
    if (recording || drawerOpen) return;
    const t = e.touches[0];
    const blockedByEdge = page === "chat" && t.clientX < EDGE_EXCLUSION_PX;
    touchStart.current = { x: t.clientX, y: t.clientY, blockedByEdge, width: window.innerWidth };
  }

  function onTouchMove(e: React.TouchEvent) {
    const start = touchStart.current;
    if (!start || start.blockedByEdge || recording || drawerOpen) return;
    const t = e.touches[0];
    const dx = t.clientX - start.x;
    const dy = t.clientY - start.y;
    if (Math.abs(dx) < Math.abs(dy)) return; // vertical scroll intent, ignore

    if (page === "chat" && dx > 0) {
      // Dragging the DAG card in from the right.
      setDragProgress(Math.min(1, dx / start.width));
    } else if (page === "dag" && dx < 0) {
      // Dragging the DAG card back out.
      setDragProgress(Math.max(0, 1 + dx / start.width));
    }
  }

  function onTouchEnd() {
    const start = touchStart.current;
    if (start && dragProgress !== null) {
      if (page === "chat" && dragProgress * start.width > SWIPE_THRESHOLD_PX) setPage("dag");
      else if (page === "dag" && (1 - dragProgress) * start.width > SWIPE_THRESHOLD_PX) setPage("chat");
    }
    touchStart.current = null;
    setDragProgress(null);
  }

  const shownProgress = dragProgress ?? (page === "dag" ? 1 : 0);
  const dagTranslateVw = (1 - shownProgress) * 100;

  return (
    <div
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={onTouchEnd}
      style={{ height: "100%", width: "100%", overflow: "hidden", position: "relative", fontFamily: "-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif" }}
    >
      <div style={{ position: "absolute", inset: 0 }}>
        <MobileChatPage
          active={active}
          sending={sending}
          onSend={sendTurn}
          onOpenDrawer={() => setDrawerOpen(true)}
          onToggleProgress={() => setProgressOpen((v) => !v)}
          progressOpen={progressOpen}
          recordingChanged={setRecording}
        />
      </div>

      <div
        style={{
          position: "absolute",
          inset: 0,
          transform: `translateX(${dagTranslateVw}vw)`,
          transition: dragProgress === null ? "transform 0.25s ease-out" : "none",
          boxShadow: shownProgress > 0 ? "-4px 0 24px rgba(0,0,0,0.12)" : "none",
        }}
      >
        <MobileDagPage active={active} onBack={() => setPage("chat")} />
      </div>

      {active?.completion.ready_for_confirmation && active.status !== "expert_confirmed" && page === "chat" && (
        <div style={{ position: "absolute", left: 14, right: 14, bottom: 78, zIndex: 5 }}>
          <button
            onClick={confirmWorkflow}
            style={{ width: "100%", border: "none", borderRadius: 8, padding: "12px 0", background: "#0ca30c", color: "#fff", fontWeight: 600, minHeight: 44 }}
          >
            确认并提交
          </button>
        </div>
      )}

      <HistorySheet
        open={drawerOpen}
        workflows={workflows}
        activeId={active?.id ?? null}
        onSelect={selectWorkflow}
        onCreate={createWorkflow}
        onClose={() => setDrawerOpen(false)}
        creating={creating}
      />

      {error && (
        <div style={{ position: "absolute", bottom: 12, left: 14, right: 14, background: "#fef2f2", border: "1px solid #fecaca", color: "#991b1b", borderRadius: 8, padding: "8px 12px", fontSize: 12, zIndex: 6 }}>
          {error}
        </div>
      )}
    </div>
  );
}
