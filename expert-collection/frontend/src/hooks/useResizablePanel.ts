// Width + collapsed state for a resizable desktop side panel, remembered per browser so the
// layout doesn't reset on every reload. localStorage is a per-viewer convenience here, not
// shared state, so failures (private browsing, blocked storage) are swallowed silently.
import { useCallback, useState } from "react";

function readStored(key: string, fallback: number): number {
  try {
    const raw = localStorage.getItem(key);
    return raw ? Number(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeStored(key: string, value: number) {
  try {
    localStorage.setItem(key, String(value));
  } catch {
    // ignore
  }
}

export function useResizablePanel(key: string, defaultWidth: number, min: number, max: number) {
  const [width, setWidthState] = useState(() => readStored(`panel-width:${key}`, defaultWidth));
  const [collapsed, setCollapsedState] = useState(() => readStored(`panel-collapsed:${key}`, 0) === 1);

  const resizeBy = useCallback(
    (deltaPx: number, direction: 1 | -1) => {
      setWidthState((prev) => {
        const next = Math.min(max, Math.max(min, prev + deltaPx * direction));
        writeStored(`panel-width:${key}`, next);
        return next;
      });
    },
    [key, min, max],
  );

  const toggleCollapsed = useCallback(() => {
    setCollapsedState((prev) => {
      const next = !prev;
      writeStored(`panel-collapsed:${key}`, next ? 1 : 0);
      return next;
    });
  }, [key]);

  return { width, collapsed, resizeBy, toggleCollapsed };
}
