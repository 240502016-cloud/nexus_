export type DesktopAction =
  | { type: "toggle-mute" }
  | { type: "toggle-deafen" }
  | { type: "ptt"; active: boolean }
  | { type: "focus-app" }
  | { type: "open-settings" }
  | { type: "update-downloaded" };

export interface DesktopKeybinds {
  pushToTalk: string;
  toggleMute: string;
  toggleDeafen: string;
  focusApp: string;
}

export interface DesktopPreferences {
  closeBehavior: "tray" | "quit";
  openAtLogin: boolean;
  startMinimized: boolean;
  autoCheckUpdates: boolean;
  overlayEnabled: boolean;
  keybinds: DesktopKeybinds;
}

export interface DesktopVoiceState {
  connected: boolean;
  channelName: string | null;
  muted: boolean;
  deafened: boolean;
  participants: Array<{
    userId: number;
    username: string;
    speaking: boolean;
    muted: boolean;
  }>;
}

export interface DesktopUpdateStatus {
  state: "idle" | "checking" | "available" | "not-available" | "downloading" | "downloaded" | "error";
  message: string;
  version?: string;
  percent?: number;
}

interface NexusDesktopBridge {
  readonly isDesktop: true;
  readonly serverUrl: string;
  readonly platform: string;
  getSecureToken(): Promise<string | null>;
  setSecureToken(token: string | null): Promise<void>;
  getPreferences(): Promise<DesktopPreferences>;
  updatePreferences(patch: Partial<DesktopPreferences>): Promise<DesktopPreferences>;
  configureKeybinds(keybinds: DesktopKeybinds): Promise<{ globalPttAvailable: boolean; errors: string[] }>;
  updateVoiceState(state: DesktopVoiceState): void;
  showNotification(options: { title: string; body: string; tag?: string }): Promise<void>;
  openOverlay(): Promise<void>;
  closeOverlay(): Promise<void>;
  checkForUpdates(): Promise<DesktopUpdateStatus>;
  installUpdate(): Promise<void>;
  onAction(listener: (action: DesktopAction) => void): () => void;
  onUpdateStatus(listener: (status: DesktopUpdateStatus) => void): () => void;
}

declare global {
  interface Window {
    nexusDesktop?: NexusDesktopBridge;
  }
}

export const desktopBridge = {
  get available(): boolean {
    return window.nexusDesktop?.isDesktop === true;
  },

  get serverUrl(): string | null {
    return window.nexusDesktop?.serverUrl ?? null;
  },

  get platform(): string {
    return window.nexusDesktop?.platform ?? "web";
  },

  async getSecureToken(): Promise<string | null> {
    return window.nexusDesktop?.getSecureToken() ?? null;
  },

  async setSecureToken(token: string | null): Promise<void> {
    await window.nexusDesktop?.setSecureToken(token);
  },

  async getPreferences(): Promise<DesktopPreferences | null> {
    return window.nexusDesktop?.getPreferences() ?? null;
  },

  async updatePreferences(patch: Partial<DesktopPreferences>): Promise<DesktopPreferences | null> {
    return window.nexusDesktop?.updatePreferences(patch) ?? null;
  },

  async configureKeybinds(
    keybinds: DesktopKeybinds,
  ): Promise<{ globalPttAvailable: boolean; errors: string[] }> {
    return window.nexusDesktop?.configureKeybinds(keybinds) ?? {
      globalPttAvailable: false,
      errors: [],
    };
  },

  updateVoiceState(state: DesktopVoiceState): void {
    window.nexusDesktop?.updateVoiceState(state);
  },

  async showNotification(options: { title: string; body: string; tag?: string }): Promise<void> {
    await window.nexusDesktop?.showNotification(options);
  },

  async openOverlay(): Promise<void> {
    await window.nexusDesktop?.openOverlay();
  },

  async closeOverlay(): Promise<void> {
    await window.nexusDesktop?.closeOverlay();
  },

  async checkForUpdates(): Promise<DesktopUpdateStatus> {
    return (
      (await window.nexusDesktop?.checkForUpdates()) ?? {
        state: "error",
        message: "Güncelleme denetimi yalnızca masaüstü uygulamasında kullanılabilir.",
      }
    );
  },

  async installUpdate(): Promise<void> {
    await window.nexusDesktop?.installUpdate();
  },

  onAction(listener: (action: DesktopAction) => void): () => void {
    return window.nexusDesktop?.onAction(listener) ?? (() => {});
  },

  onUpdateStatus(listener: (status: DesktopUpdateStatus) => void): () => void {
    return window.nexusDesktop?.onUpdateStatus(listener) ?? (() => {});
  },
};

export const DEFAULT_DESKTOP_KEYBINDS: DesktopKeybinds = {
  pushToTalk: "CapsLock",
  toggleMute: "Ctrl+Shift+KeyM",
  toggleDeafen: "Ctrl+Shift+KeyD",
  focusApp: "Ctrl+Shift+KeyN",
};

export const DEFAULT_DESKTOP_PREFERENCES: DesktopPreferences = {
  closeBehavior: "tray",
  openAtLogin: false,
  startMinimized: false,
  autoCheckUpdates: false,
  overlayEnabled: false,
  keybinds: DEFAULT_DESKTOP_KEYBINDS,
};

export function apiUrl(path: string): string {
  // Paketli uygulamada nexus:// protokolü /api isteklerini ana process üzerinden yalnız güvenilen
  // Nexus sunucusuna iletir. Böylece renderer'a CORS'u gevşetme veya remote origin yetkisi verilmez.
  return `/api${path}`;
}

export function webSocketUrl(path: string): string {
  const serverUrl = desktopBridge.serverUrl;
  if (serverUrl) {
    const url = new URL(serverUrl);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    url.pathname = `/api${path}`;
    url.search = "";
    return url.toString();
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/api${path}`;
}

export async function showSystemNotification(
  title: string,
  body: string,
  tag?: string,
): Promise<Notification | null> {
  if (desktopBridge.available) {
    await desktopBridge.showNotification({ title, body, tag });
    return null;
  }
  if (typeof Notification === "undefined" || Notification.permission !== "granted") return null;
  try {
    return new Notification(title, { body, tag });
  } catch {
    return null;
  }
}
