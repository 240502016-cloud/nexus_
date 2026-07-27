export type VoiceMode = "toggle" | "ptt";
export type ThemeMode = "dark" | "light" | "system";
export type VideoQuality = "480p" | "720p" | "1080p";
export type VideoFrameRate = 30 | 60;

export interface VideoQualityPreset {
  width: number;
  height: number;
  cameraBitrate: number;
  screenBitrate: number;
}

export const VIDEO_QUALITY_PRESETS: Record<VideoQuality, VideoQualityPreset> = {
  "480p": {
    width: 854,
    height: 480,
    cameraBitrate: 1_800_000,
    screenBitrate: 2_500_000,
  },
  "720p": {
    width: 1280,
    height: 720,
    cameraBitrate: 3_500_000,
    screenBitrate: 5_000_000,
  },
  "1080p": {
    width: 1920,
    height: 1080,
    cameraBitrate: 6_000_000,
    screenBitrate: 8_000_000,
  },
};

export interface KeyCombo {
  ctrl: boolean;
  shift: boolean;
  alt: boolean;
  code: string | null;
}

export interface VoiceSettings {
  mode: VoiceMode;
  pttCombo: KeyCombo;
  // Cihaz tercihleri (null = sistem varsayılanı). deviceId'ler tarayıcı/oturuma özgüdür.
  inputDeviceId: string | null;
  outputDeviceId: string | null;
  cameraDeviceId: string | null;
  // Kamera ve ekran paylaşımı için ücretsiz, tarayıcı tabanlı WebRTC kalite tercihleri.
  videoQuality: VideoQuality;
  videoFrameRate: VideoFrameRate;
  // Ses işleme (getUserMedia MediaTrackConstraints'e uygulanır).
  noiseSuppression: boolean;
  echoCancellation: boolean;
  autoGainControl: boolean;
  // Bildirimler.
  desktopNotifications: boolean; // mesaj ve çağrı için işletim sistemi bildirimi
  messageNotifications: boolean; // uygulama içi kenar bildirimi
  notificationSound: boolean; // yeni mesaj sesi
  callRingtone: boolean; // gelen çağrıda zil sesi
  // Görünüm.
  theme: ThemeMode;
}

const STORAGE_KEY = "nexus.voiceSettings";

export const DEFAULT_PTT_COMBO: KeyCombo = { ctrl: true, shift: true, alt: false, code: null };

export const DEFAULT_VOICE_SETTINGS: VoiceSettings = {
  mode: "toggle",
  pttCombo: DEFAULT_PTT_COMBO,
  inputDeviceId: null,
  outputDeviceId: null,
  cameraDeviceId: null,
  videoQuality: "1080p",
  videoFrameRate: 60,
  noiseSuppression: true,
  echoCancellation: true,
  autoGainControl: true,
  desktopNotifications: false,
  messageNotifications: true,
  notificationSound: true,
  callRingtone: true,
  theme: "dark",
};

function boolWithDefault(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function loadVoiceSettings(): VoiceSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_VOICE_SETTINGS;
    const parsed = JSON.parse(raw);
    return {
      mode: parsed.mode === "ptt" ? "ptt" : "toggle",
      pttCombo: {
        ctrl: Boolean(parsed.pttCombo?.ctrl),
        shift: Boolean(parsed.pttCombo?.shift),
        alt: Boolean(parsed.pttCombo?.alt),
        code: typeof parsed.pttCombo?.code === "string" ? parsed.pttCombo.code : null,
      },
      inputDeviceId: stringOrNull(parsed.inputDeviceId),
      outputDeviceId: stringOrNull(parsed.outputDeviceId),
      cameraDeviceId: stringOrNull(parsed.cameraDeviceId),
      videoQuality:
        parsed.videoQuality === "480p" || parsed.videoQuality === "720p" ? parsed.videoQuality : "1080p",
      videoFrameRate: parsed.videoFrameRate === 30 ? 30 : 60,
      noiseSuppression: boolWithDefault(parsed.noiseSuppression, true),
      echoCancellation: boolWithDefault(parsed.echoCancellation, true),
      autoGainControl: boolWithDefault(parsed.autoGainControl, true),
      desktopNotifications: boolWithDefault(parsed.desktopNotifications, false),
      messageNotifications: boolWithDefault(parsed.messageNotifications, true),
      notificationSound: boolWithDefault(parsed.notificationSound, true),
      callRingtone: boolWithDefault(parsed.callRingtone, true),
      theme: parsed.theme === "light" || parsed.theme === "system" ? parsed.theme : "dark",
    };
  } catch {
    return DEFAULT_VOICE_SETTINGS;
  }
}

export function saveVoiceSettings(settings: VoiceSettings): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

const MODIFIER_PREFIXES = ["Control", "Shift", "Alt", "Meta"];

export function isModifierCode(code: string): boolean {
  return MODIFIER_PREFIXES.some((prefix) => code.startsWith(prefix));
}

export function comboIsEmpty(combo: KeyCombo): boolean {
  return !combo.ctrl && !combo.shift && !combo.alt && !combo.code;
}

function formatCode(code: string): string {
  if (code.startsWith("Key")) return code.slice(3);
  if (code.startsWith("Digit")) return code.slice(5);
  if (code === "Space") return "Boşluk";
  return code;
}

export function comboLabel(combo: KeyCombo): string {
  const parts: string[] = [];
  if (combo.ctrl) parts.push("Ctrl");
  if (combo.shift) parts.push("Shift");
  if (combo.alt) parts.push("Alt");
  if (combo.code) parts.push(formatCode(combo.code));
  return parts.length ? parts.join(" + ") : "Atanmadı";
}
