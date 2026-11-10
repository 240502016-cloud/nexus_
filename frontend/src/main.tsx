import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { initializeTokenStorage } from "./api/client";
import { DesktopTitleBar } from "./components/DesktopTitleBar";
import { desktopBridge } from "./desktopBridge";
import "./index.css";

/**
 * Pencere odak durumunu köke yazar. Odak başka uygulamadayken (ör. oyun) App.css
 * dekoratif sonsuz animasyonları duraklatır; böylece GPU oyunla yarışmaz.
 * `document.hasFocus()` kullanılır: odak sayfadaki bir iframe'e geçince pencere hâlâ etkindir.
 */
function trackWindowFocus() {
  const root = document.documentElement;
  const sync = () => root.toggleAttribute("data-window-inactive", !document.hasFocus());
  window.addEventListener("focus", sync);
  window.addEventListener("blur", sync);
  document.addEventListener("visibilitychange", sync);
  sync();
}

async function bootstrap() {
  trackWindowFocus();
  await initializeTokenStorage();
  if (desktopBridge.available) {
    document.documentElement.classList.add("desktop-runtime");
  }
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <DesktopTitleBar />
      <App />
    </StrictMode>,
  );
}

void bootstrap();
