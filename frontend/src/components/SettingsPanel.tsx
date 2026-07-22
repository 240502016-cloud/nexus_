import { useEffect, useState } from "react";

import type { KeyCombo, VoiceSettings } from "../settings";
import { DEFAULT_VOICE_SETTINGS, comboIsEmpty, comboLabel, isModifierCode, saveVoiceSettings } from "../settings";

interface SettingsPanelProps {
  settings: VoiceSettings;
  onClose: () => void;
  onChange: (settings: VoiceSettings) => void;
}

export function SettingsPanel({ settings: initialSettings, onClose, onChange }: SettingsPanelProps) {
  const [settings, setSettings] = useState<VoiceSettings>(initialSettings);
  const [recording, setRecording] = useState(false);

  // Tuş yakalama: kullanıcı bir kombinasyonu basılı tutup bırakınca, basılı kaldığı süre
  // boyunca görülen en geniş modifier kümesi + varsa modifier olmayan tuş, yeni combo olur.
  useEffect(() => {
    if (!recording) return;

    let maxCombo: KeyCombo = { ctrl: false, shift: false, alt: false, code: null };
    let sawKey = false;

    function handleKeyDown(event: KeyboardEvent) {
      event.preventDefault();
      sawKey = true;
      maxCombo = {
        ctrl: maxCombo.ctrl || event.ctrlKey,
        shift: maxCombo.shift || event.shiftKey,
        alt: maxCombo.alt || event.altKey,
        code: isModifierCode(event.code) ? maxCombo.code : event.code,
      };
    }
    function handleKeyUp(event: KeyboardEvent) {
      event.preventDefault();
      if (sawKey && !comboIsEmpty(maxCombo)) {
        setRecording(false);
        setSettings((prev) => ({ ...prev, pttCombo: maxCombo }));
      }
    }
    function handleBlur() {
      setRecording(false);
    }

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    window.addEventListener("blur", handleBlur);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
      window.removeEventListener("blur", handleBlur);
    };
  }, [recording]);

  function handleSave() {
    saveVoiceSettings(settings);
    onChange(settings);
    onClose();
  }

  function handleReset() {
    setSettings(DEFAULT_VOICE_SETTINGS);
  }

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-panel" onClick={(event) => event.stopPropagation()}>
        <header className="settings-panel__header">
          <h2>Ses Ayarları</h2>
          <button className="settings-panel__close" onClick={onClose} aria-label="Kapat">
            ✕
          </button>
        </header>

        <div className="settings-panel__section">
          <label className="settings-panel__radio">
            <input
              type="radio"
              checked={settings.mode === "toggle"}
              onChange={() => setSettings((prev) => ({ ...prev, mode: "toggle" }))}
            />
            Sürekli açık — elle sustur/aç
          </label>
          <label className="settings-panel__radio">
            <input
              type="radio"
              checked={settings.mode === "ptt"}
              onChange={() => setSettings((prev) => ({ ...prev, mode: "ptt" }))}
            />
            Bas-konuş (Push-to-talk)
          </label>
        </div>

        {settings.mode === "ptt" ? (
          <div className="settings-panel__section">
            <div className="settings-panel__ptt-key">
              <span>Tuş: </span>
              <strong>{recording ? "Tuşlara basın..." : comboLabel(settings.pttCombo)}</strong>
            </div>
            <button onClick={() => setRecording(true)} disabled={recording}>
              {recording ? "Dinleniyor..." : "Tuşu değiştir"}
            </button>
            <p className="settings-panel__hint">
              Sadece sekme odaktayken çalışır. Sekme arka plandayken (ör. tam ekran bir oyun)
              tarayıcı güvenlik kısıtı nedeniyle tuş yakalanamaz.
            </p>
          </div>
        ) : null}

        <div className="settings-panel__actions">
          <button onClick={handleReset}>Varsayılana dön</button>
          <button className="settings-panel__save" onClick={handleSave}>
            Kaydet
          </button>
        </div>
      </div>
    </div>
  );
}
