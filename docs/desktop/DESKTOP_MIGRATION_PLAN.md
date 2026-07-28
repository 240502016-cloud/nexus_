# Nexus Windows Desktop Client

## Repository inventory

- Frontend: React 18, TypeScript and Vite. State is held in React hooks and local storage.
- Backend: FastAPI, SQLAlchemy and PostgreSQL. The desktop client does not require a database
  migration or a new API contract.
- Realtime: the global `/api/gateway` WebSocket carries presence, messages and calls. Voice uses
  `/api/channels/{id}/voice` plus the existing WebRTC mesh implementation.
- Authentication: the existing Bearer token remains authoritative. The web client keeps using
  local storage; the desktop client moves the token to Electron `safeStorage` (Windows DPAPI).
- Media: `getUserMedia`, `getDisplayMedia`, `RTCPeerConnection` and `setSinkId` are all already
  isolated in frontend hooks and can be reused.
- Build: Vite produces the web client. Docker/Caddy continues serving that build unchanged.

## Framework decision

Electron is selected instead of Tauri for the first desktop release.

| Criterion | Electron | Tauri 2 |
| --- | --- | --- |
| Existing React reuse | Direct | Direct |
| Windows media compatibility | Bundled Chromium, closest to the tested client | Depends on installed WebView2 |
| Screen sharing control | Official `desktopCapturer` and session API | WebView2/version-dependent |
| Global input | Electron shortcut API plus an isolated native hook adapter | Plugin supports press/release |
| Tray/window/notifications | Built in | Plugins |
| Installer/update | Mature NSIS and signed update metadata | Good, but adds Rust/toolchain work |
| Footprint | Larger | Smaller |
| Repository/toolchain fit | Node is present | Rust is not present |

Nexus is media-heavy, so predictable Chromium/WebRTC behavior and low migration risk outweigh the
larger installer and memory footprint. The decision can be revisited if WebView2 screen capture
becomes a verified drop-in replacement.

## Migration plan

1. Keep the React feature tree shared by web and desktop.
2. Add a small `desktopBridge` abstraction. Browser builds receive safe no-op fallbacks.
3. Resolve REST/WSS endpoints from the desktop runtime without changing existing API paths.
4. Package the Vite output behind a privileged local `nexus://app` scheme; never load arbitrary
   remote pages with native privileges.
5. Add the Electron main/preload processes for the window, tray, native notifications, global
   keybinds, startup, overlay, secure token storage and updates.
6. Add desktop-only Settings sections and a compact draggable title bar.
7. Produce a per-user NSIS installer with Start Menu/uninstall support. Auto-update remains opt-in
   until a signed release feed is configured.

## Security boundaries

- `nodeIntegration` is disabled, `contextIsolation` and renderer sandboxing are enabled.
- Only `nexus://app` (and the local Vite origin in development) may request media permissions or
  invoke the preload bridge.
- Navigation and new-window creation are denied except for explicitly opened HTTPS links, which
  are sent to the system browser.
- The server URL must be HTTPS outside local development.
- The token is encrypted with the OS credential mechanism and is never placed in application
  source, command-line arguments or updater configuration.
- Auto-update artifacts must be code-signed for production. The updater additionally verifies the
  checksum in generated release metadata.

## Known first-release boundary

Global keyboard press/release and Mouse4/Mouse5 use the optional `uiohook-napi` native adapter. If
the native adapter cannot load on a machine, mute/deafen/focus shortcuts fall back to Electron's
global shortcut API. Hold-to-talk is then limited to the focused window and the Settings UI reports
that reduced mode instead of silently behaving as global PTT.
