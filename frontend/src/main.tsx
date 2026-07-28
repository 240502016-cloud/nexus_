import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { initializeTokenStorage } from "./api/client";
import { DesktopTitleBar } from "./components/DesktopTitleBar";
import { desktopBridge } from "./desktopBridge";
import "./index.css";

async function bootstrap() {
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
