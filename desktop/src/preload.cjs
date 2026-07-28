const { contextBridge, ipcRenderer } = require("electron");

const serverArgument = process.argv.find((argument) => argument.startsWith("--nexus-server-url="));
const serverUrl = serverArgument
  ? decodeURIComponent(serverArgument.slice("--nexus-server-url=".length))
  : "https://cekin.gen.tr";

function subscribe(channel, listener) {
  const wrapped = (_event, payload) => listener(payload);
  ipcRenderer.on(channel, wrapped);
  return () => ipcRenderer.removeListener(channel, wrapped);
}

contextBridge.exposeInMainWorld("nexusDesktop", Object.freeze({
  isDesktop: true,
  platform: process.platform,
  serverUrl,
  getSecureToken: () => ipcRenderer.invoke("auth:get-token"),
  setSecureToken: (token) => ipcRenderer.invoke("auth:set-token", token),
  getPreferences: () => ipcRenderer.invoke("preferences:get"),
  updatePreferences: (patch) => ipcRenderer.invoke("preferences:update", patch),
  configureKeybinds: (keybinds) => ipcRenderer.invoke("keybinds:configure", keybinds),
  updateVoiceState: (state) => ipcRenderer.send("voice:update-state", state),
  sendOverlayAction: (action) => ipcRenderer.send("overlay:action", action),
  showNotification: (options) => ipcRenderer.invoke("notification:show", options),
  openOverlay: () => ipcRenderer.invoke("overlay:open"),
  closeOverlay: () => ipcRenderer.invoke("overlay:close"),
  checkForUpdates: () => ipcRenderer.invoke("updates:check"),
  installUpdate: () => ipcRenderer.invoke("updates:install"),
  onAction: (listener) => subscribe("desktop:action", listener),
  onVoiceState: (listener) => subscribe("overlay:voice-state", listener),
  onUpdateStatus: (listener) => subscribe("updates:status", listener),
}));
