// Desktop and mobile are separate bundles (C2): a phone never downloads the desktop modules
// (Dashboard, experiment center, admin pages) and vice versa.
import { lazy, Suspense } from "react";
import { useIsMobile } from "./hooks/useIsMobile";

const DesktopApp = lazy(() => import("./pages/DesktopApp").then((m) => ({ default: m.DesktopApp })));
const MobileApp = lazy(() => import("./mobile/MobileApp").then((m) => ({ default: m.MobileApp })));

export function App() {
  const isMobile = useIsMobile();
  return <Suspense fallback={null}>{isMobile ? <MobileApp /> : <DesktopApp />}</Suspense>;
}
