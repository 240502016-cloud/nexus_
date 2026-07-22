export type VoiceMode = "toggle" | "ptt";

export interface KeyCombo {
  ctrl: boolean;
  shift: boolean;
  alt: boolean;
  code: string | null;
}

export interface VoiceSettings {
  mode: VoiceMode;
  pttCombo: KeyCombo;
}

const STORAGE_KEY = "nexus.voiceSettings";

export const DEFAULT_PTT_COMBO: KeyCombo = { ctrl: true, shift: true, alt: false, code: null };

export const DEFAULT_VOICE_SETTINGS: VoiceSettings = {
  mode: "toggle",
  pttCombo: DEFAULT_PTT_COMBO,
};

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
