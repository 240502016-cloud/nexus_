import {
  app,
  BrowserWindow,
  Menu,
  Notification,
  Tray,
  desktopCapturer,
  dialog,
  globalShortcut,
  ipcMain,
  nativeImage,
  net,
  protocol,
  safeStorage,
  session,
  shell,
} from "electron";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, normalize, relative } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const CURRENT_DIR = dirname(fileURLToPath(import.meta.url));
const DEV_URL = process.env.NEXUS_DESKTOP_DEV_URL || "";
const DEFAULT_SERVER_URL = "https://cekin.gen.tr";
const SERVER_URL = validateServerUrl(process.env.NEXUS_SERVER_URL || DEFAULT_SERVER_URL);
const DEV_RENDERER_ORIGIN = DEV_URL ? new URL(DEV_URL).origin : null;

protocol.registerSchemesAsPrivileged([
  {
    scheme: "nexus",
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
      stream: true,
    },
  },
  {
    scheme: "nexus-desktop",
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
    },
  },
]);

const DEFAULT_PREFERENCES = Object.freeze({
  closeBehavior: "tray",
  openAtLogin: false,
  startMinimized: false,
  autoCheckUpdates: false,
  overlayEnabled: false,
  keybinds: {
    pushToTalk: "CapsLock",
    toggleMute: "Ctrl+Shift+KeyM",
    toggleDeafen: "Ctrl+Shift+KeyD",
    focusApp: "Ctrl+Shift+KeyN",
  },
});

let mainWindow = null;
let overlayWindow = null;
let tray = null;
let isQuitting = false;
let preferences = null;
let nativeHook = null;
let activeInputIds = new Set();
let lastVoiceState = {
  connected: false,
  channelName: null,
  muted: true,
  deafened: false,
  participants: [],
};
let updateStatus = { state: "idle", message: "Güncelleme denetimi hazır." };
let updater = null;

function validateServerUrl(value) {
  const url = new URL(value);
  const localDevelopment = url.hostname === "localhost" || url.hostname === "127.0.0.1";
  if (url.protocol !== "https:" && !(localDevelopment && url.protocol === "http:")) {
    throw new Error("NEXUS_SERVER_URL HTTPS kullanmalıdır (localhost geliştirmesi hariç).");
  }
  return url.origin;
}

function isTrustedRenderer(event) {
  return isTrustedRendererUrl(event.senderFrame.url);
}

function isTrustedRendererUrl(value) {
  try {
    const url = new URL(value);
    if (url.protocol === "nexus:" && url.host === "app") return true;
    if (url.protocol === "nexus-desktop:" && url.host === "app-desktop") return true;
    return Boolean(DEV_RENDERER_ORIGIN && url.origin === DEV_RENDERER_ORIGIN);
  } catch {
    return false;
  }
}

function assertTrustedRenderer(event) {
  if (!isTrustedRenderer(event)) throw new Error("Güvenilmeyen renderer IPC isteği reddedildi.");
}

function settingsPath() {
  return join(app.getPath("userData"), "desktop-settings.json");
}

function tokenPath() {
  return join(app.getPath("userData"), "secure-token.json");
}

function readJson(path, fallback) {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return fallback;
  }
}

function sanitizeKeybinds(value) {
  const incoming = value && typeof value === "object" ? value : {};
  const fallback = DEFAULT_PREFERENCES.keybinds;
  const clean = {};
  for (const key of ["pushToTalk", "toggleMute", "toggleDeafen", "focusApp"]) {
    const candidate = incoming[key];
    clean[key] =
      typeof candidate === "string" && candidate.length <= 80 && /^[A-Za-z0-9+]+$/.test(candidate)
        ? candidate
        : fallback[key];
  }
  return clean;
}

function sanitizePreferences(value) {
  const incoming = value && typeof value === "object" ? value : {};
  return {
    closeBehavior: incoming.closeBehavior === "quit" ? "quit" : "tray",
    openAtLogin: Boolean(incoming.openAtLogin),
    startMinimized: Boolean(incoming.startMinimized),
    autoCheckUpdates: Boolean(incoming.autoCheckUpdates),
    overlayEnabled: Boolean(incoming.overlayEnabled),
    keybinds: sanitizeKeybinds(incoming.keybinds),
  };
}

function savePreferences() {
  writeFileSync(settingsPath(), `${JSON.stringify(preferences, null, 2)}\n`, "utf8");
}

function applyLoginPreference() {
  app.setLoginItemSettings({
    openAtLogin: preferences.openAtLogin,
    args: preferences.startMinimized ? ["--hidden"] : [],
  });
}

function rendererUrlAllowed(url) {
  return isTrustedRendererUrl(url);
}

function createMainWindow() {
  const window = new BrowserWindow({
    title: "Nexus",
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 640,
    show: false,
    backgroundColor: "#0f1117",
    autoHideMenuBar: true,
    titleBarStyle: "hidden",
    titleBarOverlay: {
      color: "#11131a",
      symbolColor: "#f4f5f7",
      height: 36,
    },
    webPreferences: {
      preload: join(CURRENT_DIR, "preload.cjs"),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
      additionalArguments: [`--nexus-server-url=${encodeURIComponent(SERVER_URL)}`],
    },
  });

  window.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://")) void shell.openExternal(url);
    return { action: "deny" };
  });
  window.webContents.on("will-navigate", (event, url) => {
    if (!rendererUrlAllowed(url)) event.preventDefault();
  });
  window.webContents.on("will-attach-webview", (event) => event.preventDefault());
  window.on("close", (event) => {
    if (!isQuitting && preferences.closeBehavior === "tray") {
      event.preventDefault();
      window.hide();
    }
  });
  window.on("show", () => window.webContents.send("desktop:action", { type: "focus-app" }));

  if (DEV_URL) void window.loadURL(DEV_URL);
  else void window.loadURL("nexus://app/");

  if (process.argv.includes("--smoke-test")) {
    window.webContents.once("did-finish-load", () => {
      process.stdout.write("NEXUS_DESKTOP_SMOKE_OK\n");
      setTimeout(() => app.exit(0), 300);
    });
    window.webContents.once("did-fail-load", (_event, code, description) => {
      process.stderr.write(`NEXUS_DESKTOP_SMOKE_FAILED ${code} ${description}\n`);
      app.exit(2);
    });
  }

  const startHidden =
    process.argv.includes("--hidden") ||
    process.argv.includes("--smoke-test") ||
    (preferences.startMinimized && app.getLoginItemSettings().wasOpenedAtLogin);
  if (!startHidden) {
    window.once("ready-to-show", () => window.show());
  }
  return window;
}

function createOverlayWindow() {
  if (overlayWindow && !overlayWindow.isDestroyed()) {
    overlayWindow.show();
    overlayWindow.focus();
    return overlayWindow;
  }
  overlayWindow = new BrowserWindow({
    title: "Nexus Mini",
    width: 300,
    height: 330,
    minWidth: 240,
    minHeight: 180,
    maxWidth: 440,
    maxHeight: 620,
    frame: false,
    transparent: true,
    resizable: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    backgroundColor: "#00000000",
    webPreferences: {
      preload: join(CURRENT_DIR, "preload.cjs"),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
      additionalArguments: [`--nexus-server-url=${encodeURIComponent(SERVER_URL)}`],
    },
  });
  overlayWindow.setAlwaysOnTop(true, "floating");
  overlayWindow.on("closed", () => {
    overlayWindow = null;
  });
  void overlayWindow.loadURL("nexus://app-desktop/overlay.html");
  overlayWindow.webContents.once("did-finish-load", () => {
    overlayWindow?.webContents.send("overlay:voice-state", lastVoiceState);
  });
  return overlayWindow;
}

function createTray() {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">
      <rect width="32" height="32" rx="9" fill="#7c5cff"/>
      <path d="M8 23V9h4l8 8.7V9h4v14h-3.8L12 14.2V23z" fill="white"/>
    </svg>`;
  const icon = nativeImage.createFromDataURL(`data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`);
  tray = new Tray(icon.resize({ width: 20, height: 20 }));
  tray.setToolTip("Nexus");
  tray.on("double-click", showMainWindow);
  refreshTrayMenu();
}

function refreshTrayMenu() {
  if (!tray) return;
  const template = [
    { label: "Nexus'u Aç", click: showMainWindow },
    { type: "separator" },
    {
      label: lastVoiceState.muted ? "Mikrofonu Aç" : "Mikrofonu Kapat",
      enabled: lastVoiceState.connected,
      click: () => sendAction({ type: "toggle-mute" }),
    },
    {
      label: lastVoiceState.deafened ? "Sağırı Kapat" : "Sağırlaştır",
      enabled: lastVoiceState.connected,
      click: () => sendAction({ type: "toggle-deafen" }),
    },
    {
      label: "Mini Pencere",
      type: "checkbox",
      checked: Boolean(overlayWindow && !overlayWindow.isDestroyed() && overlayWindow.isVisible()),
      click: (item) => (item.checked ? createOverlayWindow() : overlayWindow?.hide()),
    },
    { type: "separator" },
    {
      label: "Ayarlar",
      click: () => {
        showMainWindow();
        sendAction({ type: "open-settings" });
      },
    },
    {
      label: "Çıkış",
      click: () => {
        isQuitting = true;
        app.quit();
      },
    },
  ];
  tray.setContextMenu(Menu.buildFromTemplate(template));
}

function showMainWindow() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
}

function sendAction(action) {
  if (action.type === "focus-app") showMainWindow();
  mainWindow?.webContents.send("desktop:action", action);
}

function normalizeBinding(value) {
  return value
    .split("+")
    .map((part) => part.trim())
    .filter(Boolean);
}

function bindingSatisfied(value) {
  const parts = normalizeBinding(value);
  const expectsCtrl = parts.includes("Ctrl");
  const expectsShift = parts.includes("Shift");
  const expectsAlt = parts.includes("Alt");
  const primary = parts.find((part) => !["Ctrl", "Shift", "Alt"].includes(part));
  return (
    parts.length > 0 &&
    (!primary || activeInputIds.has(primary)) &&
    (!expectsCtrl || activeInputIds.has("ControlLeft") || activeInputIds.has("ControlRight")) &&
    (!expectsShift || activeInputIds.has("ShiftLeft") || activeInputIds.has("ShiftRight")) &&
    (!expectsAlt || activeInputIds.has("AltLeft") || activeInputIds.has("AltRight"))
  );
}

function electronAccelerator(binding) {
  return normalizeBinding(binding)
    .map((part) => {
      if (part === "Ctrl") return "CommandOrControl";
      if (part.startsWith("Key")) return part.slice(3);
      if (part.startsWith("Digit")) return part.slice(5);
      return part;
    })
    .join("+");
}

function hookCodeName(event, keyEnum) {
  for (const [name, value] of Object.entries(keyEnum)) {
    if (value === event.keycode && Number.isNaN(Number(name))) {
      if (/^[A-Z]$/.test(name)) return `Key${name}`;
      if (/^[0-9]$/.test(name)) return `Digit${name}`;
      const aliases = {
        Ctrl: "ControlLeft",
        CtrlRight: "ControlRight",
        Shift: "ShiftLeft",
        ShiftRight: "ShiftRight",
        Alt: "AltLeft",
        AltRight: "AltRight",
        Space: "Space",
        CapsLock: "CapsLock",
      };
      return aliases[name] || name;
    }
  }
  return null;
}

async function configureKeybinds(keybinds) {
  const clean = sanitizeKeybinds(keybinds);
  preferences.keybinds = clean;
  savePreferences();
  globalShortcut.unregisterAll();
  activeInputIds.clear();
  if (nativeHook) {
    try {
      nativeHook.stop();
      nativeHook.removeAllListeners();
    } catch {
      // Hook zaten durmuş olabilir.
    }
    nativeHook = null;
  }

  const errors = [];
  const duplicates = new Map();
  for (const [action, binding] of Object.entries(clean)) {
    const normalized = binding.toLowerCase();
    if (duplicates.has(normalized)) errors.push(`${binding}: ${duplicates.get(normalized)} ile çakışıyor.`);
    else duplicates.set(normalized, action);
  }

  try {
    const module = await import("uiohook-napi");
    const { uIOhook, UiohookKey } = module;
    nativeHook = uIOhook;
    const bindingState = {
      pushToTalk: false,
      toggleMute: false,
      toggleDeafen: false,
      focusApp: false,
    };

    const processInput = (code, pressed) => {
      if (pressed) activeInputIds.add(code);
      else activeInputIds.delete(code);

      const pttActive = bindingSatisfied(clean.pushToTalk);
      if (pttActive !== bindingState.pushToTalk) {
        bindingState.pushToTalk = pttActive;
        sendAction({ type: "ptt", active: pttActive });
      }
      for (const [name, action] of [
        ["toggleMute", "toggle-mute"],
        ["toggleDeafen", "toggle-deafen"],
        ["focusApp", "focus-app"],
      ]) {
        const satisfied = bindingSatisfied(clean[name]);
        if (satisfied && !bindingState[name]) sendAction({ type: action });
        bindingState[name] = satisfied;
      }
    };

    uIOhook.on("keydown", (event) => {
      const code = hookCodeName(event, UiohookKey);
      if (code) processInput(code, true);
    });
    uIOhook.on("keyup", (event) => {
      const code = hookCodeName(event, UiohookKey);
      if (code) processInput(code, false);
    });
    uIOhook.on("mousedown", (event) => {
      const code = event.button === 4 ? "Mouse4" : event.button === 5 ? "Mouse5" : null;
      if (code) processInput(code, true);
    });
    uIOhook.on("mouseup", (event) => {
      const code = event.button === 4 ? "Mouse4" : event.button === 5 ? "Mouse5" : null;
      if (code) processInput(code, false);
    });
    uIOhook.start();
    return { globalPttAvailable: errors.length === 0, errors };
  } catch (error) {
    errors.push(`Global bas-konuş sürücüsü yüklenemedi: ${error instanceof Error ? error.message : String(error)}`);
  }

  for (const [name, action] of [
    ["toggleMute", "toggle-mute"],
    ["toggleDeafen", "toggle-deafen"],
    ["focusApp", "focus-app"],
  ]) {
    const binding = clean[name];
    try {
      if (!globalShortcut.register(electronAccelerator(binding), () => sendAction({ type: action }))) {
        errors.push(`${binding}: başka bir uygulama tarafından kullanılıyor.`);
      }
    } catch {
      errors.push(`${binding}: bu sistemde desteklenmiyor.`);
    }
  }
  return { globalPttAvailable: false, errors };
}

async function configureUpdater() {
  if (!app.isPackaged) return;
  try {
    const electronUpdater = await import("electron-updater");
    updater = electronUpdater.autoUpdater;
    updater.autoDownload = true;
    updater.autoInstallOnAppQuit = true;
    updater.on("checking-for-update", () => publishUpdateStatus({ state: "checking", message: "Güncelleme denetleniyor…" }));
    updater.on("update-available", (info) =>
      publishUpdateStatus({ state: "available", message: `${info.version} sürümü indiriliyor.`, version: info.version }),
    );
    updater.on("update-not-available", () =>
      publishUpdateStatus({ state: "not-available", message: "Nexus güncel." }),
    );
    updater.on("download-progress", (progress) =>
      publishUpdateStatus({
        state: "downloading",
        message: `Güncelleme indiriliyor: %${Math.round(progress.percent)}`,
        percent: progress.percent,
      }),
    );
    updater.on("update-downloaded", (info) => {
      publishUpdateStatus({
        state: "downloaded",
        message: `${info.version} hazır. Yeniden başlatarak kurulabilir.`,
        version: info.version,
      });
      sendAction({ type: "update-downloaded" });
    });
    updater.on("error", (error) =>
      publishUpdateStatus({ state: "error", message: `Güncelleme hatası: ${error.message}` }),
    );
    if (preferences.autoCheckUpdates) void updater.checkForUpdatesAndNotify();
  } catch (error) {
    publishUpdateStatus({
      state: "error",
      message: `Güncelleme sistemi başlatılamadı: ${error instanceof Error ? error.message : String(error)}`,
    });
  }
}

function publishUpdateStatus(status) {
  updateStatus = status;
  mainWindow?.webContents.send("updates:status", status);
}

function installProtocolHandlers() {
  const frontendRoot = DEV_URL ? null : join(process.resourcesPath, "frontend");
  const desktopRoot = join(CURRENT_DIR, "..", "assets");

  const serve = (root, request, fallbackToIndex) => {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/api/")) {
      const target = `${SERVER_URL}${url.pathname}${url.search}`;
      const init = {
        method: request.method,
        headers: request.headers,
      };
      if (request.method !== "GET" && request.method !== "HEAD") init.body = request.body;
      return net.fetch(target, init);
    }
    const requested = decodeURIComponent(url.pathname === "/" ? "/index.html" : url.pathname);
    const resolved = normalize(join(root, requested));
    if (relative(root, resolved).startsWith("..")) return new Response("Forbidden", { status: 403 });
    const finalPath = existsSync(resolved) ? resolved : fallbackToIndex ? join(root, "index.html") : resolved;
    if (!existsSync(finalPath)) return new Response("Not found", { status: 404 });
    return net.fetch(pathToFileURL(finalPath).toString());
  };

  if (frontendRoot) {
    protocol.handle("nexus", (request) => serve(frontendRoot, request, true));
  }
  protocol.handle("nexus-desktop", (request) => serve(desktopRoot, request, false));
}

function configureSessionSecurity() {
  const allowedOrigin = (url) => {
    return isTrustedRendererUrl(url);
  };

  session.defaultSession.setPermissionCheckHandler((_webContents, permission, requestingOrigin) => {
    return allowedOrigin(requestingOrigin) && ["media", "notifications", "fullscreen"].includes(permission);
  });
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    callback(
      allowedOrigin(webContents.getURL()) && ["media", "notifications", "fullscreen"].includes(permission),
    );
  });
  session.defaultSession.setDisplayMediaRequestHandler(async (request, callback) => {
    if (!allowedOrigin(request.securityOrigin) || !request.userGesture || !request.videoRequested) {
      callback({});
      return;
    }
    try {
      const sources = await desktopCapturer.getSources({
        types: ["screen", "window"],
        thumbnailSize: { width: 0, height: 0 },
        fetchWindowIcons: false,
      });
      const visibleSources = sources.slice(0, 24);
      const choice = await dialog.showMessageBox(mainWindow, {
        type: "question",
        title: "Ekran paylaşımı",
        message: "Paylaşılacak ekranı veya pencereyi seçin",
        buttons: [...visibleSources.map((source) => source.name.slice(0, 70)), "İptal"],
        cancelId: visibleSources.length,
        defaultId: 0,
        noLink: true,
      });
      const source = visibleSources[choice.response];
      callback(source ? { video: source } : {});
    } catch {
      callback({});
    }
  });
}

function registerIpcHandlers() {
  ipcMain.handle("auth:get-token", (event) => {
    assertTrustedRenderer(event);
    if (!safeStorage.isEncryptionAvailable()) return null;
    const stored = readJson(tokenPath(), null);
    if (!stored?.encrypted) return null;
    try {
      return safeStorage.decryptString(Buffer.from(stored.encrypted, "base64"));
    } catch {
      return null;
    }
  });
  ipcMain.handle("auth:set-token", (event, token) => {
    assertTrustedRenderer(event);
    if (token !== null && (typeof token !== "string" || token.length > 16_384)) {
      throw new Error("Geçersiz token.");
    }
    if (token === null) {
      writeFileSync(tokenPath(), "{}\n", "utf8");
      return;
    }
    if (!safeStorage.isEncryptionAvailable()) throw new Error("Windows güvenli depolama kullanılamıyor.");
    const encrypted = safeStorage.encryptString(token).toString("base64");
    writeFileSync(tokenPath(), `${JSON.stringify({ encrypted })}\n`, "utf8");
  });
  ipcMain.handle("preferences:get", (event) => {
    assertTrustedRenderer(event);
    return preferences;
  });
  ipcMain.handle("preferences:update", async (event, patch) => {
    assertTrustedRenderer(event);
    const previousAutoCheck = preferences.autoCheckUpdates;
    preferences = sanitizePreferences({ ...preferences, ...(patch || {}) });
    savePreferences();
    applyLoginPreference();
    await configureKeybinds(preferences.keybinds);
    if (!previousAutoCheck && preferences.autoCheckUpdates && updater) void updater.checkForUpdatesAndNotify();
    refreshTrayMenu();
    return preferences;
  });
  ipcMain.handle("keybinds:configure", async (event, keybinds) => {
    assertTrustedRenderer(event);
    return configureKeybinds(keybinds);
  });
  ipcMain.on("voice:update-state", (event, state) => {
    if (!isTrustedRenderer(event)) return;
    if (!state || typeof state !== "object") return;
    lastVoiceState = {
      connected: Boolean(state.connected),
      channelName: typeof state.channelName === "string" ? state.channelName.slice(0, 120) : null,
      muted: Boolean(state.muted),
      deafened: Boolean(state.deafened),
      participants: Array.isArray(state.participants)
        ? state.participants.slice(0, 100).map((participant) => ({
            userId: Number(participant.userId),
            username: String(participant.username).slice(0, 80),
            speaking: Boolean(participant.speaking),
            muted: Boolean(participant.muted),
          }))
        : [],
    };
    overlayWindow?.webContents.send("overlay:voice-state", lastVoiceState);
    refreshTrayMenu();
  });
  ipcMain.on("overlay:action", (event, action) => {
    if (!isTrustedRenderer(event)) return;
    if (action === "toggle-mute") sendAction({ type: "toggle-mute" });
    if (action === "toggle-deafen") sendAction({ type: "toggle-deafen" });
  });
  ipcMain.handle("notification:show", (event, options) => {
    assertTrustedRenderer(event);
    if (!Notification.isSupported()) return;
    const notification = new Notification({
      title: String(options?.title || "Nexus").slice(0, 120),
      body: String(options?.body || "").slice(0, 500),
      silent: false,
      timeoutType: "default",
    });
    notification.on("click", showMainWindow);
    notification.show();
  });
  ipcMain.handle("overlay:open", (event) => {
    assertTrustedRenderer(event);
    createOverlayWindow();
  });
  ipcMain.handle("overlay:close", (event) => {
    assertTrustedRenderer(event);
    overlayWindow?.hide();
  });
  ipcMain.handle("updates:check", async (event) => {
    assertTrustedRenderer(event);
    if (!app.isPackaged) return { state: "error", message: "Güncelleme yalnızca kurulu sürümde denetlenir." };
    if (!updater) return updateStatus;
    await updater.checkForUpdates();
    return updateStatus;
  });
  ipcMain.handle("updates:install", (event) => {
    assertTrustedRenderer(event);
    if (updater && updateStatus.state === "downloaded") {
      isQuitting = true;
      updater.quitAndInstall(false, true);
    }
  });
}

app.whenReady().then(async () => {
  preferences = sanitizePreferences(readJson(settingsPath(), DEFAULT_PREFERENCES));
  applyLoginPreference();
  installProtocolHandlers();
  configureSessionSecurity();
  registerIpcHandlers();
  mainWindow = createMainWindow();
  createTray();
  const keybindResult = await configureKeybinds(preferences.keybinds);
  if (process.argv.includes("--smoke-test") && !keybindResult.globalPttAvailable) {
    process.stderr.write(`NEXUS_DESKTOP_KEYBIND_FAILED ${keybindResult.errors.join(" ")}\n`);
    app.exit(3);
    return;
  }
  await configureUpdater();

  app.on("activate", () => {
    if (!mainWindow || mainWindow.isDestroyed()) mainWindow = createMainWindow();
    else showMainWindow();
  });
});

app.on("before-quit", () => {
  isQuitting = true;
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
  try {
    nativeHook?.stop();
    nativeHook?.removeAllListeners();
  } catch {
    // Uygulama kapanıyor.
  }
});

app.on("window-all-closed", () => {
  // Windows'ta tray uygulamanın yaşam döngüsünü sürdürür.
});
