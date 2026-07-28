import { useEffect, useState } from "react";

import { desktopBridge } from "../desktopBridge";

export function DesktopTitleBar() {
  const [title, setTitle] = useState(document.title || "Nexus");

  useEffect(() => {
    if (!desktopBridge.available) return;
    const titleElement = document.querySelector("title");
    if (!titleElement) return;
    const observer = new MutationObserver(() => setTitle(document.title || "Nexus"));
    observer.observe(titleElement, { childList: true });
    return () => observer.disconnect();
  }, []);

  if (!desktopBridge.available) return null;
  return (
    <div className="desktop-titlebar" aria-label="Nexus pencere başlığı">
      <div className="desktop-titlebar__mark" aria-hidden="true">N</div>
      <span className="desktop-titlebar__name">Nexus</span>
      <span className="desktop-titlebar__context">{title === "Nexus" ? "İletişim Platformu" : title}</span>
    </div>
  );
}
