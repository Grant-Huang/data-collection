import { useIsMobile } from "./hooks/useIsMobile";
import { SessionPage } from "./pages/SessionPage";
import { MobileApp } from "./mobile/MobileApp";

export function App() {
  const isMobile = useIsMobile();
  return isMobile ? <MobileApp /> : <SessionPage />;
}
