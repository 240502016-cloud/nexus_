import { useCallback, useEffect, useRef, useState } from "react";

import { SINK_ID_SUPPORTED, useMediaDevices } from "../hooks/useMediaDevices";
import type { SelfStatus } from "../hooks/useGateway";
import type { KeyCombo, VoiceSettings } from "../settings";
import {
  DEFAULT_VOICE_SETTINGS,
  VIDEO_QUALITY_PRESETS,
  comboIsEmpty,
  comboLabel,
  isModifierCode,
  saveVoiceSettings,
} from "../settings";
import type { User } from "../types";
import { AccountSettings } from "./AccountSettings";
import { Icon } from "./Icon";

type SettingsTab = "account" | "status" | "voice" | "notifications" | "appearance";

interface SettingsPanelProps {
  settings: VoiceSettings;
  currentUser: User;
  onUserUpdated: (user: User) => void;
  onClose: () => void;
  onChange: (settings: VoiceSettings) => void;
  selfStatus: SelfStatus;
  onStatusChange: (status: SelfStatus["status"], custom: string) => void;
}

async function setElementSink(el: HTMLMediaElement, deviceId: string | null): Promise<void> {
  const withSink = el as HTMLMediaElement & { setSinkId?: (id: string) => Promise<void> };
  if (typeof withSink.setSinkId !== "function") return;
  try {
    await withSink.setSinkId(deviceId ?? "");
  } catch {
    /* yok say */
  }
}

export function SettingsPanel({
  settings: initialSettings,
  currentUser,
  onUserUpdated,
  onClose,
  onChange,
  selfStatus,
  onStatusChange,
}: SettingsPanelProps) {
  const [settings, setSettings] = useState<VoiceSettings>(initialSettings);
  const [recording, setRecording] = useState(false);
  const [tab, setTab] = useState<SettingsTab>("account");
  const [status, setStatus] = useState(selfStatus.status);
  const [customStatus, setCustomStatus] = useState(selfStatus.custom);
  const [notifPermission, setNotifPermission] = useState<NotificationPermission | "unsupported">(
    typeof Notification === "undefined" ? "unsupported" : Notification.permission,
  );

  async function requestNotifPermission() {
    if (typeof Notification === "undefined") return;
    const result = await Notification.requestPermission();
    setNotifPermission(result);
  }

  const { devices, permissionGranted, error: deviceError, requestPermission } = useMediaDevices();

  // --- Mikrofon test (canlı seviye) ve kamera önizleme kaynakları ---
  const [micLevel, setMicLevel] = useState(0);
  const [micTesting, setMicTesting] = useState(false);
  const [camPreviewing, setCamPreviewing] = useState(false);
  const micTestRef = useRef<{ ctx: AudioContext; stream: MediaStream; raf: number } | null>(null);
  const camStreamRef = useRef<MediaStream | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const update = useCallback((patch: Partial<VoiceSettings>) => {
    setSettings((prev) => ({ ...prev, ...patch }));
  }, []);

  const stopMicTest = useCallback(() => {
    const t = micTestRef.current;
    if (t) {
      cancelAnimationFrame(t.raf);
      t.stream.getTracks().forEach((track) => track.stop());
      void t.ctx.close();
      micTestRef.current = null;
    }
    setMicTesting(false);
    setMicLevel(0);
  }, []);

  const startMicTest = useCallback(async () => {
    stopMicTest();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: settings.inputDeviceId ? { deviceId: { exact: settings.inputDeviceId } } : true,
      });
      const ctx = new AudioContext();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);
      const buffer = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteFrequencyData(buffer);
        const avg = buffer.reduce((s, v) => s + v, 0) / buffer.length;
        setMicLevel(Math.min(100, Math.round((avg / 128) * 100)));
        micTestRef.current = { ctx, stream, raf: requestAnimationFrame(tick) };
      };
      micTestRef.current = { ctx, stream, raf: requestAnimationFrame(tick) };
      setMicTesting(true);
    } catch {
      setMicTesting(false);
    }
  }, [settings.inputDeviceId, stopMicTest]);

  const stopCamPreview = useCallback(() => {
    camStreamRef.current?.getTracks().forEach((t) => t.stop());
    camStreamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setCamPreviewing(false);
  }, []);

  const startCamPreview = useCallback(async () => {
    stopCamPreview();
    try {
      const preset = VIDEO_QUALITY_PRESETS[settings.videoQuality];
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          ...(settings.cameraDeviceId ? { deviceId: { exact: settings.cameraDeviceId } } : {}),
          width: { ideal: preset.width, max: preset.width },
          height: { ideal: preset.height, max: preset.height },
          frameRate: { ideal: settings.videoFrameRate, max: settings.videoFrameRate },
          aspectRatio: { ideal: 16 / 9 },
        },
      });
      camStreamRef.current = stream;
      if (videoRef.current) videoRef.current.srcObject = stream;
      setCamPreviewing(true);
    } catch {
      setCamPreviewing(false);
    }
  }, [settings.cameraDeviceId, settings.videoFrameRate, settings.videoQuality, stopCamPreview]);

  const testSpeaker = useCallback(async () => {
    const ctx = new AudioContext();
    const dest = ctx.createMediaStreamDestination();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 440;
    const now = ctx.currentTime;
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.25, now + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.5);
    osc.connect(gain);
    gain.connect(dest);
    const el = new Audio();
    el.srcObject = dest.stream;
    await setElementSink(el, settings.outputDeviceId);
    osc.start();
    osc.stop(now + 0.5);
    try {
      await el.play();
    } catch {
      /* yok say */
    }
    window.setTimeout(() => void ctx.close(), 800);
  }, [settings.outputDeviceId]);

  // Panel kapanınca test kaynaklarını serbest bırak (memory/stream sızıntısını önle).
  useEffect(() => {
    return () => {
      stopMicTest();
      stopCamPreview();
    };
  }, [stopMicTest, stopCamPreview]);

  // PTT tuş yakalama.
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
        code: isModifierCode(event.code) ? maxCombo.code : maxCombo.code ?? event.code,
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
    stopMicTest();
    stopCamPreview();
    saveVoiceSettings(settings);
    onChange(settings);
    onStatusChange(status, customStatus.trim());
    onClose();
  }

  function handleReset() {
    setSettings(DEFAULT_VOICE_SETTINGS);
  }

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-panel settings-panel--wide" onClick={(event) => event.stopPropagation()}>
        <header className="settings-panel__header">
          <h2>Ayarlar</h2>
          <button className="settings-panel__close" onClick={onClose} aria-label="Kapat">
            <Icon name="close" />
          </button>
        </header>

        <nav className="settings-panel__tabs">
          <button
            className={tab === "status" ? "settings-panel__tab active" : "settings-panel__tab"}
            onClick={() => setTab("status")}
          >
            Durum
          </button>
          <button
            className={tab === "account" ? "settings-panel__tab active" : "settings-panel__tab"}
            onClick={() => setTab("account")}
          >
            Hesabım
          </button>
          <button
            className={tab === "voice" ? "settings-panel__tab active" : "settings-panel__tab"}
            onClick={() => setTab("voice")}
          >
            Ses ve Video
          </button>
          <button
            className={tab === "notifications" ? "settings-panel__tab active" : "settings-panel__tab"}
            onClick={() => setTab("notifications")}
          >
            Bildirimler
          </button>
          <button
            className={tab === "appearance" ? "settings-panel__tab active" : "settings-panel__tab"}
            onClick={() => setTab("appearance")}
          >
            Görünüm
          </button>
        </nav>

        {tab === "account" ? (
          <AccountSettings currentUser={currentUser} onUserUpdated={onUserUpdated} />
        ) : (
          <>
        {tab === "status" ? (
          <div className="settings-panel__section">
            <h3 className="settings-panel__section-title">Durum ve görünürlük</h3>
            <label className="settings-panel__field">
              <span>Durum</span>
              <select value={status} onChange={(event) => setStatus(event.target.value as SelfStatus["status"])}>
                <option value="online">Çevrimiçi</option>
                <option value="idle">Boşta</option>
                <option value="dnd">Rahatsız etmeyin</option>
                <option value="invisible">Görünmez</option>
              </select>
            </label>
            <label className="settings-panel__field">
              <span>Özel durum</span>
              <input value={customStatus} maxLength={128} onChange={(event) => setCustomStatus(event.target.value)} placeholder="Bugün ne yapıyorsun?" />
            </label>
            <p className="settings-panel__hint">Rahatsız etmeyin seçiliyken mesaj ve arama bildirimi gönderilmez.</p>
          </div>
        ) : null}
        {tab === "voice" ? (
          <>
        {/* Konuşma modu */}
        <div className="settings-panel__section">
          <h3 className="settings-panel__section-title">Konuşma modu</h3>
          <label className="settings-panel__radio">
            <input
              type="radio"
              checked={settings.mode === "toggle"}
              onChange={() => update({ mode: "toggle" })}
            />
            Ses algılama (sürekli açık — elle sustur/aç)
          </label>
          <label className="settings-panel__radio">
            <input type="radio" checked={settings.mode === "ptt"} onChange={() => update({ mode: "ptt" })} />
            Bas-konuş (Push-to-talk)
          </label>
          {settings.mode === "ptt" ? (
            <div className="settings-panel__ptt-key">
              <span>Tuş: </span>
              <strong>{recording ? "Tuşlara basın..." : comboLabel(settings.pttCombo)}</strong>
              <button onClick={() => setRecording(true)} disabled={recording}>
                {recording ? "Dinleniyor..." : "Değiştir"}
              </button>
            </div>
          ) : null}
        </div>

        {/* Cihazlar */}
        <div className="settings-panel__section">
          <h3 className="settings-panel__section-title">Cihazlar</h3>
          {!permissionGranted ? (
            <div className="settings-panel__notice-row">
              <span>Cihaz adlarını görmek için mikrofon/kamera iznine ihtiyaç var.</span>
              <button onClick={requestPermission}>İzin ver</button>
            </div>
          ) : null}
          {deviceError ? <p className="settings-panel__error-text">{deviceError}</p> : null}

          <label className="settings-panel__field">
            <span>Mikrofon</span>
            <select
              value={settings.inputDeviceId ?? ""}
              onChange={(e) => update({ inputDeviceId: e.target.value || null })}
            >
              <option value="">Sistem varsayılanı</option>
              {devices.microphones.map((d) => (
                <option key={d.deviceId} value={d.deviceId}>
                  {d.label}
                </option>
              ))}
            </select>
          </label>
          <div className="settings-panel__test-row">
            <button onClick={micTesting ? stopMicTest : startMicTest}>
              {micTesting ? "Testi durdur" : "Mikrofonu test et"}
            </button>
            <div className="settings-panel__meter" aria-label="Mikrofon seviyesi">
              <div className="settings-panel__meter-fill" style={{ width: `${micLevel}%` }} />
            </div>
          </div>

          <label className="settings-panel__field">
            <span>Hoparlör (çıkış)</span>
            <select
              value={settings.outputDeviceId ?? ""}
              onChange={(e) => update({ outputDeviceId: e.target.value || null })}
              disabled={!SINK_ID_SUPPORTED}
            >
              <option value="">Sistem varsayılanı</option>
              {devices.speakers.map((d) => (
                <option key={d.deviceId} value={d.deviceId}>
                  {d.label}
                </option>
              ))}
            </select>
          </label>
          {SINK_ID_SUPPORTED ? (
            <div className="settings-panel__test-row">
              <button onClick={testSpeaker}><Icon name="volume" /> Hoparlörü test et</button>
            </div>
          ) : (
            <p className="settings-panel__hint">
              Bu tarayıcı ses çıkışı seçimini (setSinkId) desteklemiyor; sistem varsayılanı kullanılır.
            </p>
          )}

          <label className="settings-panel__field">
            <span>Kamera</span>
            <select
              value={settings.cameraDeviceId ?? ""}
              onChange={(e) => update({ cameraDeviceId: e.target.value || null })}
            >
              <option value="">Sistem varsayılanı</option>
              {devices.cameras.map((d) => (
                <option key={d.deviceId} value={d.deviceId}>
                  {d.label}
                </option>
              ))}
            </select>
          </label>
          <div className="settings-panel__quality-grid">
            <label className="settings-panel__field">
              <span>Görüntü kalitesi</span>
              <select
                value={settings.videoQuality}
                onChange={(event) =>
                  update({ videoQuality: event.target.value as VoiceSettings["videoQuality"] })
                }
              >
                <option value="480p">480p · Veri tasarrufu</option>
                <option value="720p">720p · Dengeli</option>
                <option value="1080p">1080p · Yüksek kalite</option>
              </select>
            </label>
            <label className="settings-panel__field">
              <span>Kare hızı</span>
              <select
                value={settings.videoFrameRate}
                onChange={(event) =>
                  update({ videoFrameRate: Number(event.target.value) as VoiceSettings["videoFrameRate"] })
                }
              >
                <option value={30}>30 FPS · Dengeli</option>
                <option value={60}>60 FPS · Akıcı</option>
              </select>
            </label>
          </div>
          <p className="settings-panel__hint">
            Bu tercih hem kameraya hem ekran paylaşımına uygulanır. 1080p/60 FPS daha fazla bağlantı
            hızı ve işlem gücü kullanır; hiçbir seçenek ücretli servis gerektirmez.
          </p>
          <div className="settings-panel__test-row">
            <button onClick={camPreviewing ? stopCamPreview : startCamPreview}>
              {camPreviewing ? "Önizlemeyi kapat" : "Kamera önizleme"}
            </button>
          </div>
          {camPreviewing ? (
            <video ref={videoRef} autoPlay playsInline muted className="settings-panel__cam-preview" />
          ) : null}
        </div>

        {/* Ses işleme */}
        <div className="settings-panel__section">
          <h3 className="settings-panel__section-title">Ses işleme</h3>
          <label className="settings-panel__radio">
            <input
              type="checkbox"
              checked={settings.noiseSuppression}
              onChange={(e) => update({ noiseSuppression: e.target.checked })}
            />
            Gürültü engelleme
          </label>
          <label className="settings-panel__radio">
            <input
              type="checkbox"
              checked={settings.echoCancellation}
              onChange={(e) => update({ echoCancellation: e.target.checked })}
            />
            Yankı engelleme
          </label>
          <label className="settings-panel__radio">
            <input
              type="checkbox"
              checked={settings.autoGainControl}
              onChange={(e) => update({ autoGainControl: e.target.checked })}
            />
            Otomatik kazanç kontrolü
          </label>
          <p className="settings-panel__hint">
            Bu seçenekler tarayıcının standart ses işleme (MediaTrackConstraints) desteğini kullanır;
            değişiklik kaydedilince görüşmeden çıkmadan uygulanır.
          </p>
        </div>

          </>
        ) : null}

        {tab === "notifications" ? (
          <div className="settings-panel__section">
            <h3 className="settings-panel__section-title">Bildirimler</h3>
            <div className="settings-panel__notice-row">
              <span>
                Tarayıcı bildirim izni:{" "}
                <strong>
                  {notifPermission === "granted"
                    ? "Verildi"
                    : notifPermission === "denied"
                      ? "Reddedildi"
                      : notifPermission === "unsupported"
                        ? "Desteklenmiyor"
                        : "İstenmedi"}
                </strong>
              </span>
              {notifPermission === "default" ? (
                <button onClick={requestNotifPermission}>İzin iste</button>
              ) : null}
            </div>
            {notifPermission === "denied" ? (
              <p className="settings-panel__hint">
                Bildirimler tarayıcıdan engellenmiş; site izinlerinden yeniden açabilirsiniz.
              </p>
            ) : null}
            <label className="settings-panel__radio">
              <input
                type="checkbox"
                checked={settings.desktopNotifications}
                disabled={notifPermission !== "granted"}
                onChange={(e) => update({ desktopNotifications: e.target.checked })}
              />
              Sekme arka plandayken mesajlar ve aramalar için sistem bildirimi
            </label>
            <label className="settings-panel__radio">
              <input
                type="checkbox"
                checked={settings.notificationSound}
                onChange={(e) => update({ notificationSound: e.target.checked })}
              />
              Yeni mesaj sesi
            </label>
            <label className="settings-panel__radio">
              <input
                type="checkbox"
                checked={settings.callRingtone}
                onChange={(e) => update({ callRingtone: e.target.checked })}
              />
              Gelen aramada zil sesi
            </label>
            <p className="settings-panel__hint">
              Rahatsız etmeyin durumundayken mesaj ve arama bildirimlerinin tamamı sessize alınır.
            </p>
          </div>
        ) : null}

        {tab === "appearance" ? (
          <div className="settings-panel__section">
            <h3 className="settings-panel__section-title">Tema</h3>
            <label className="settings-panel__radio">
              <input
                type="radio"
                checked={settings.theme === "system"}
                onChange={() => update({ theme: "system" })}
              />
              Sistem temasını kullan
            </label>
            <label className="settings-panel__radio">
              <input
                type="radio"
                checked={settings.theme === "dark"}
                onChange={() => update({ theme: "dark" })}
              />
              Koyu
            </label>
            <label className="settings-panel__radio">
              <input
                type="radio"
                checked={settings.theme === "light"}
                onChange={() => update({ theme: "light" })}
              />
              Açık
            </label>
            <p className="settings-panel__hint">Değişiklik kaydedilince uygulanır.</p>
          </div>
        ) : null}

        <div className="settings-panel__actions">
          <button onClick={handleReset}>Varsayılana dön</button>
          <button className="settings-panel__save" onClick={handleSave}>
            Kaydet
          </button>
        </div>
          </>
        )}
      </div>
    </div>
  );
}
