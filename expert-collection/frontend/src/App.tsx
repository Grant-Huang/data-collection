import { useIsMobile } from "./hooks/useIsMobile";
import { DesktopApp } from "./pages/DesktopApp";
import { MobileApp } from "./mobile/MobileApp";

export function App() {
  const isMobile = useIsMobile();
  return isMobile ? <MobileApp /> : <DesktopApp />;
}
