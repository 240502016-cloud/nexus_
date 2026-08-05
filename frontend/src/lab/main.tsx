import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { initializeTokenStorage } from "../api/client";
import { desktopBridge } from "../desktopBridge";
import "../index.css";
import "../App.css";
import "./lab.css";
import { LabApp } from "./LabApp";

/**
 * Nexus Lab kendi HTML belgesidir ve ana uygulamadan bağımsız bir pencerede açılır.
 * Aynı origin'de çalıştığı için oturum jetonu, tema tercihi ve API istemcisi olduğu gibi
 * paylaşılır; ayrı bir giriş akışı veya jeton devri gerekmez.
 */
async function bootstrap() {
  await initializeTokenStorage();
  if (desktopBridge.available) {
    document.documentElement.classList.add("desktop-runtime");
  }
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <LabApp />
    </StrictMode>,
  );
}

void bootstrap();
