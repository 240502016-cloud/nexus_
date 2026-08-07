export type VoiceMode = "toggle" | "ptt";
/**
 * Tema kimlikleri.
 *
 * `dark` / `light` / `system` mevcut davranıştır ve hiç değişmedi. Diğer dördü
 * `themes.css` içinde tanımlı, tamamen eklemeli temalardır: kendi
 * `:root[data-theme="..."]` seçicileri altında yaşarlar, varsayılan iki temaya
 * dokunmazlar.
 */
export type ThemeMode = "dark" | "light" | "system" | "space" | "bespoke" | "feline" | "razor";

export interface ThemeOption {
  value: ThemeMode;
  label: string;
  hint: string;
  /** Seçicideki önizleme noktaları: zemin, yüzey, vurgu. */
  swatch: [string, string, string];
}

export const THEME_OPTIONS: ThemeOption[] = [
  { value: "system",  label: "Sistem",        hint: "İşletim sisteminin tercihini izler",        swatch: ["#1e1f22", "#313338", "#5865f2"] },
  { value: "dark",    label: "Koyu",          hint: "Varsayılan mor vurgulu koyu tema",          swatch: ["#080b14", "#1d2234", "#8168ff"] },
  { value: "light",   label: "Açık",          hint: "Varsayılan açık tema",                      swatch: ["#edf0f7", "#ffffff", "#6656e8"] },
  { value: "space",   label: "Derin Uzay",    hint: "Karanlık nebula, oksitlenmiş bakır vurgu",  swatch: ["#07090f", "#141b28", "#c77b4e"] },
  { value: "bespoke", label: "Özel Dikim",    hint: "Mat deri dokusu, eskitilmiş altın, serif",  swatch: ["#14120e", "#201d17", "#b08d4f"] },
  { value: "feline",  label: "Feline",        hint: "Latte ve krem, line-art detaylar",          swatch: ["#ede8e0", "#f8f5f0", "#a6714a"] },
  { value: "razor",   label: "Jilet",         hint: "Keskin köşe, tek piksel çizgi, saf kontrast", swatch: ["#000000", "#101010", "#0f5bff"] },
];

const THEME_VALUES = THEME_OPTIONS.map((option) => option.value);

export function isThemeMode(value: unknown): value is ThemeMode {
  return typeof value === "string" && THEME_VALUES.includes(value as ThemeMode);
}
export type VideoQuality = "480p" | "720p" | "1080p" | "1440p" | "2160p";
export type VideoFrameRate = 30 | 60;
export type ScreenShareMode = "motion" | "detail";
export type DesktopCloseBehavior = "tray" | "quit";

export interface VideoQualityPreset {
  width: number;
  height: number;
  cameraBitrate: number;
  screenBitrate: number;
  /** Ayarlar ekranında gösterilen kısa açıklama. */
  label: string;
  /** Yüksek yükleme bant genişliği gerektiren, mesh topolojide dikkatli kullanılacak seviye. */
  demanding?: boolean;
}

export const VIDEO_QUALITY_ORDER: VideoQuality[] = [
  "480p",
  "720p",
  "1080p",
  "1440p",
  "2160p",
];

/**
 * Bitrate değerleri **tavan**dır, taban değil: WebRTC ağ koşullarına göre aşağı iner.
 * Medya sunucudan geçmez (mesh P2P), bu yüzden sınırlayıcı olan tek şey kullanıcının
 * yükleme hızıdır. Katılımcı başına ayrı encode olduğu için kalabalık odalarda
 * yüksek seviyeler bilinçli seçilmelidir.
 */
export const VIDEO_QUALITY_PRESETS: Record<VideoQuality, VideoQualityPreset> = {
  "480p": {
    width: 854,
    height: 480,
    cameraBitrate: 2_000_000,
    screenBitrate: 3_000_000,
    label: "480p · en düşük veri kullanımı",
  },
  "720p": {
    width: 1280,
    height: 720,
    cameraBitrate: 4_000_000,
    screenBitrate: 6_000_000,
    label: "720p · dengeli",
  },
  "1080p": {
    width: 1920,
    height: 1080,
    cameraBitrate: 7_000_000,
    screenBitrate: 10_000_000,
    label: "1080p · önerilen",
  },
  "1440p": {
    width: 2560,
    height: 1440,
    cameraBitrate: 12_000_000,
    screenBitrate: 18_000_000,
    label: "1440p · keskin metin, yüksek yükleme",
    demanding: true,
  },
  "2160p": {
    width: 3840,
    height: 2160,
    cameraBitrate: 20_000_000,
    screenBitrate: 32_000_000,
    label: "4K · çok yüksek yükleme, az kişilik odalar",
    demanding: true,
  },
};

/**
 * Giden ses için Opus bitrate tavanı (bit/sn).
 *
 * Mikrofon + soundboard + yayın sesi tek track'te karışır. Yalnız konuşma varken düşük
 * bitrate yeterlidir; ekran/sekme sesi (müzik, oyun) devredeyken bitrate yükseltilmezse
 * yayın sesi belirgin biçimde boğuk duyulur.
 */
export const AUDIO_BITRATE = {
  voice: 64_000,
  withStream: 160_000,
} as const;

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
  inputVolume: number;
  outputVolume: number;
  // Kamera ve ekran paylaşımı için ücretsiz, tarayıcı tabanlı WebRTC kalite tercihleri.
  videoQuality: VideoQuality;
  videoFrameRate: VideoFrameRate;
  screenShareMode: ScreenShareMode;
  /** Ekran/sekme sesi paylaşılırken giden ses bitrate'ini yükseltir. */
  highFidelityStreamAudio: boolean;
  // Ses işleme (getUserMedia MediaTrackConstraints'e uygulanır).
  noiseSuppression: boolean;
  echoCancellation: boolean;
  autoGainControl: boolean;
  // Bildirimler.
  desktopNotifications: boolean; // mesaj ve çağrı için işletim sistemi bildirimi
  messageNotifications: boolean; // uygulama içi kenar bildirimi
  mentionNotifications: boolean; // @mention için sistem bildirimi
  notificationSound: boolean; // yeni mesaj sesi
  callRingtone: boolean; // gelen çağrıda zil sesi
  // Görünüm.
  theme: ThemeMode;
  // Masaüstü runtime tarafından uygulanır; web istemcisinde güvenli biçimde etkisizdir.
  desktopCloseBehavior: DesktopCloseBehavior;
  desktopOpenAtLogin: boolean;
  desktopStartMinimized: boolean;
  desktopAutoCheckUpdates: boolean;
  desktopOverlayEnabled: boolean;
  desktopPushToTalkKey: string;
  desktopToggleMuteKey: string;
  desktopToggleDeafenKey: string;
  desktopFocusAppKey: string;
}

export function buildAudioConstraints(settings: VoiceSettings): MediaTrackConstraints {
  return {
    ...(settings.inputDeviceId ? { deviceId: { exact: settings.inputDeviceId } } : {}),
    noiseSuppression: settings.noiseSuppression,
    echoCancellation: settings.echoCancellation,
    autoGainControl: settings.autoGainControl,
    channelCount: { ideal: 1 },
    sampleRate: { ideal: 48_000 },
    sampleSize: { ideal: 16 },
  };
}

const STORAGE_KEY = "nexus.voiceSettings";

export const DEFAULT_PTT_COMBO: KeyCombo = { ctrl: true, shift: true, alt: false, code: null };

export const DEFAULT_VOICE_SETTINGS: VoiceSettings = {
  mode: "toggle",
  pttCombo: DEFAULT_PTT_COMBO,
  inputDeviceId: null,
  outputDeviceId: null,
  cameraDeviceId: null,
  inputVolume: 100,
  outputVolume: 100,
  videoQuality: "1080p",
  videoFrameRate: 60,
  screenShareMode: "motion",
  highFidelityStreamAudio: true,
  noiseSuppression: true,
  echoCancellation: true,
  autoGainControl: true,
  desktopNotifications: false,
  messageNotifications: true,
  mentionNotifications: true,
  notificationSound: true,
  callRingtone: true,
  theme: "dark",
  desktopCloseBehavior: "tray",
  desktopOpenAtLogin: false,
  desktopStartMinimized: false,
  desktopAutoCheckUpdates: false,
  desktopOverlayEnabled: false,
  desktopPushToTalkKey: "CapsLock",
  desktopToggleMuteKey: "Ctrl+Shift+KeyM",
  desktopToggleDeafenKey: "Ctrl+Shift+KeyD",
  desktopFocusAppKey: "Ctrl+Shift+KeyN",
};

function boolWithDefault(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function numberInRange(value: unknown, fallback: number, minimum = 0, maximum = 200): number {
  return typeof value === "number" && Number.isFinite(value)
    ? Math.max(minimum, Math.min(maximum, Math.round(value)))
    : fallback;
}

function keybindWithDefault(value: unknown, fallback: string): string {
  return typeof value === "string" && value.length > 0 && value.length <= 80 ? value : fallback;
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
      inputVolume: numberInRange(parsed.inputVolume, 100),
      outputVolume: numberInRange(parsed.outputVolume, 100),
      videoQuality: VIDEO_QUALITY_ORDER.includes(parsed.videoQuality as VideoQuality)
        ? (parsed.videoQuality as VideoQuality)
        : "1080p",
      highFidelityStreamAudio: boolWithDefault(parsed.highFidelityStreamAudio, true),
      videoFrameRate: parsed.videoFrameRate === 30 ? 30 : 60,
      screenShareMode: parsed.screenShareMode === "detail" ? "detail" : "motion",
      noiseSuppression: boolWithDefault(parsed.noiseSuppression, true),
      echoCancellation: boolWithDefault(parsed.echoCancellation, true),
      autoGainControl: boolWithDefault(parsed.autoGainControl, true),
      desktopNotifications: boolWithDefault(parsed.desktopNotifications, false),
      messageNotifications: boolWithDefault(parsed.messageNotifications, true),
      mentionNotifications: boolWithDefault(parsed.mentionNotifications, true),
      notificationSound: boolWithDefault(parsed.notificationSound, true),
      callRingtone: boolWithDefault(parsed.callRingtone, true),
      theme: isThemeMode(parsed.theme) ? parsed.theme : "dark",
      desktopCloseBehavior: parsed.desktopCloseBehavior === "quit" ? "quit" : "tray",
      desktopOpenAtLogin: boolWithDefault(parsed.desktopOpenAtLogin, false),
      desktopStartMinimized: boolWithDefault(parsed.desktopStartMinimized, false),
      desktopAutoCheckUpdates: boolWithDefault(parsed.desktopAutoCheckUpdates, false),
      desktopOverlayEnabled: boolWithDefault(parsed.desktopOverlayEnabled, false),
      desktopPushToTalkKey: keybindWithDefault(parsed.desktopPushToTalkKey, "CapsLock"),
      desktopToggleMuteKey: keybindWithDefault(parsed.desktopToggleMuteKey, "Ctrl+Shift+KeyM"),
      desktopToggleDeafenKey: keybindWithDefault(parsed.desktopToggleDeafenKey, "Ctrl+Shift+KeyD"),
      desktopFocusAppKey: keybindWithDefault(parsed.desktopFocusAppKey, "Ctrl+Shift+KeyN"),
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
