import { useCallback, useEffect, useRef, useState } from "react";

import { SINK_ID_SUPPORTED, useMediaDevices } from "../hooks/useMediaDevices";
import type { SelfStatus } from "../hooks/useGateway";
import { desktopBridge } from "../desktopBridge";
import type { DesktopUpdateStatus } from "../desktopBridge";
import type { KeyCombo, VoiceSettings } from "../settings";
import {
  DEFAULT_VOICE_SETTINGS,
  THEME_OPTIONS,
  VIDEO_QUALITY_ORDER,
  VIDEO_QUALITY_PRESETS,
  buildAudioConstraints,
  comboIsEmpty,
  comboLabel,
  isModifierCode,
  saveVoiceSettings,
} from "../settings";
import type { User } from "../types";
import { AccountSettings } from "./AccountSettings";
import { Icon } from "./Icon";

type SettingsTab =
  | "account"
  | "status"
  | "voice"
  | "notifications"
  | "appearance"
  | "keybinds"
  | "windows"
  | "advanced";

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
    desktopBridge.available
      ? "granted"
      : typeof Notification === "undefined"
        ? "unsupported"
        : Notification.permission,
  );
  const [desktopFeedback, setDesktopFeedback] = useState<string | null>(null);
  const [updateStatus, setUpdateStatus] = useState<DesktopUpdateStatus>({
    state: "idle",
    message: "Henüz güncelleme denetlenmedi.",
  });

  async function requestNotifPermission() {
    if (desktopBridge.available) {
      setNotifPermission("granted");
      return;
    }
    if (typeof Notification === "undefined") return;
    const result = await Notification.requestPermission();
    setNotifPermission(result);
  }

  const { devices, permissionGranted, error: deviceError, requestPermission } = useMediaDevices();

  useEffect(() => desktopBridge.onUpdateStatus(setUpdateStatus), []);

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
        audio: buildAudioConstraints(settings),
      });
      const ctx = new AudioContext();
      const source = ctx.createMediaStreamSource(stream);
      const gain = ctx.createGain();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      gain.gain.value = Math.max(0, Math.min(2, settings.inputVolume / 100));
      source.connect(gain);
      gain.connect(analyser);
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
  }, [
    settings.autoGainControl,
    settings.echoCancellation,
    settings.inputDeviceId,
    settings.inputVolume,
    settings.noiseSuppression,
    stopMicTest,
  ]);

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

  async function handleSave() {
    stopMicTest();
    stopCamPreview();
    if (desktopBridge.available) {
      const keybinds = {
        pushToTalk: settings.desktopPushToTalkKey,
        toggleMute: settings.desktopToggleMuteKey,
        toggleDeafen: settings.desktopToggleDeafenKey,
        focusApp: settings.desktopFocusAppKey,
      };
      const duplicateCount = new Set(Object.values(keybinds).map((value) => value.toLowerCase())).size;
      if (duplicateCount !== Object.keys(keybinds).length) {
        setDesktopFeedback("Aynı kısayol iki eyleme atanamaz.");
        return;
      }
      const result = await desktopBridge.configureKeybinds(keybinds);
      await desktopBridge.updatePreferences({
        closeBehavior: settings.desktopCloseBehavior,
        openAtLogin: settings.desktopOpenAtLogin,
        startMinimized: settings.desktopStartMinimized,
        autoCheckUpdates: settings.desktopAutoCheckUpdates,
        overlayEnabled: settings.desktopOverlayEnabled,
      });
      if (result.errors.length) {
        setDesktopFeedback(result.errors.join(" "));
        return;
      }
    }
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
          {desktopBridge.available ? (
            <>
              <button
                className={tab === "keybinds" ? "settings-panel__tab active" : "settings-panel__tab"}
                onClick={() => setTab("keybinds")}
              >
                Kısayollar
              </button>
              <button
                className={tab === "windows" ? "settings-panel__tab active" : "settings-panel__tab"}
                onClick={() => setTab("windows")}
              >
                Windows
              </button>
              <button
                className={tab === "advanced" ? "settings-panel__tab active" : "settings-panel__tab"}
                onClick={() => setTab("advanced")}
              >
                Gelişmiş
              </button>
            </>
          ) : null}
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
          <label className="settings-panel__field">
            <span>Mikrofon giriş seviyesi · %{settings.inputVolume}</span>
            <input
              type="range"
              min={0}
              max={200}
              value={settings.inputVolume}
              onChange={(event) => update({ inputVolume: Number(event.target.value) })}
            />
          </label>
          <p className="settings-panel__hint">
            %100 doğal seviye, %101–200 yazılımsal yükseltmedir. Yüksek değerlerde dip ses de
            büyüyebileceği için mikrofon testiyle ayarlayın.
          </p>
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
          <label className="settings-panel__field">
            <span>Çıkış seviyesi · %{settings.outputVolume}</span>
            <input
              type="range"
              min={0}
              max={100}
              value={settings.outputVolume}
              onChange={(event) => update({ outputVolume: Number(event.target.value) })}
            />
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
                {VIDEO_QUALITY_ORDER.map((quality) => (
                  <option key={quality} value={quality}>
                    {VIDEO_QUALITY_PRESETS[quality].label}
                  </option>
                ))}
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
            <label className="settings-panel__field">
              <span>Yayın türü</span>
              <select
                value={settings.screenShareMode}
                onChange={(event) =>
                  update({ screenShareMode: event.target.value as VoiceSettings["screenShareMode"] })
                }
              >
                <option value="motion">Oyun · Akıcılığı koru</option>
                <option value="detail">Metin · Netliği koru</option>
              </select>
            </label>
          </div>
          <label className="settings-panel__radio">
            <input
              type="checkbox"
              checked={settings.highFidelityStreamAudio}
              onChange={(e) => update({ highFidelityStreamAudio: e.target.checked })}
            />
            Yüksek kaliteli yayın sesi (ekran/sekme sesi paylaşırken)
          </label>
          <p className="settings-panel__hint">
            Çözünürlük ve FPS kameraya ve yayına uygulanır. Oyun modu zorlanınca önce çözünürlüğü,
            Metin modu ise önce kare hızını düşürür. Bu değerler bir <b>tavan</b>dır: bağlantı
            yetmezse görüntü otomatik olarak aşağı iner, donmaz.
            {VIDEO_QUALITY_PRESETS[settings.videoQuality].demanding ? (
              <>
                {" "}
                <b>1440p ve 4K</b> yüksek yükleme hızı ister. Görüntü herkese ayrı ayrı
                kodlandığı için kalabalık odalarda 1080p daha akıcı olur.
              </>
            ) : null}
            {" "}Yüksek kaliteli yayın sesi müzik ve oyun sesini belirgin biçimde netleştirir,
            karşılığında ses için biraz daha bant genişliği kullanır. Hiçbir seçenek ücretli
            servis gerektirmez.
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
            Gürültü engelleme + düşük frekans temizleme
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
            Tarayıcının standart ses işleme desteğine ek olarak gürültü engelleme açıkken masa/klavye
            titreşimi gibi düşük frekanslar yumuşakça süzülür ve ani seviye sıçramaları dengelenir.
            Değişiklik kaydedilince görüşmeden çıkmadan uygulanır.
          </p>
        </div>

          </>
        ) : null}

        {tab === "notifications" ? (
          <div className="settings-panel__section">
            <h3 className="settings-panel__section-title">Bildirimler</h3>
            <div className="settings-panel__notice-row">
              <span>
                {desktopBridge.available ? "Windows bildirimleri: " : "Tarayıcı bildirim izni: "}
                <strong>
                  {desktopBridge.available
                    ? "Hazır"
                    : notifPermission === "granted"
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
              {desktopBridge.available ? "Nexus arka plandayken" : "Sekme arka plandayken"} mesajlar
              ve aramalar için sistem bildirimi
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
                checked={settings.mentionNotifications}
                onChange={(e) => update({ mentionNotifications: e.target.checked })}
              />
              Bana @mention geldiğinde bildirim göster
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
            <div className="theme-picker" role="radiogroup" aria-label="Tema">
              {THEME_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  role="radio"
                  aria-checked={settings.theme === option.value}
                  className={settings.theme === option.value
                    ? "theme-card theme-card--active"
                    : "theme-card"}
                  onClick={() => update({ theme: option.value })}
                >
                  <span className="theme-card__swatch" aria-hidden="true">
                    {option.swatch.map((color, index) => (
                      <span key={index} style={{ background: color }} />
                    ))}
                  </span>
                  <span className="theme-card__name">{option.label}</span>
                  <span className="theme-card__hint">{option.hint}</span>
                </button>
              ))}
            </div>
            <p className="settings-panel__hint">
              Tema anında uygulanır. Koyu ve Açık varsayılan temalardır; diğerleri ayrı bir
              katman olarak eklenmiştir ve varsayılanları değiştirmez.
            </p>
          </div>
        ) : null}

        {tab === "keybinds" ? (
          <div className="settings-panel__section">
            <h3 className="settings-panel__section-title">Global kısayollar</h3>
            <p className="settings-panel__hint">
              Biçim örnekleri: <b>CapsLock</b>, <b>Mouse4</b>, <b>Ctrl+Shift+KeyM</b>.
              Global bas-konuş tuşa basıldığı ve bırakıldığı anı izler; oyun öndeyken de çalışır.
            </p>
            {[
              ["Bas-konuş", "desktopPushToTalkKey"],
              ["Mikrofonu aç / kapat", "desktopToggleMuteKey"],
              ["Sağırlaştır", "desktopToggleDeafenKey"],
              ["Nexus'u öne getir", "desktopFocusAppKey"],
            ].map(([label, key]) => (
              <label className="settings-panel__field" key={key}>
                <span>{label}</span>
                <input
                  value={settings[key as keyof VoiceSettings] as string}
                  onChange={(event) =>
                    update({ [key]: event.target.value } as Partial<VoiceSettings>)
                  }
                  spellCheck={false}
                />
              </label>
            ))}
            {desktopFeedback ? <p className="settings-panel__error-text">{desktopFeedback}</p> : null}
          </div>
        ) : null}

        {tab === "windows" ? (
          <div className="settings-panel__section">
            <h3 className="settings-panel__section-title">Windows davranışı</h3>
            <label className="settings-panel__field">
              <span>Kapat düğmesi</span>
              <select
                value={settings.desktopCloseBehavior}
                onChange={(event) =>
                  update({
                    desktopCloseBehavior: event.target.value as VoiceSettings["desktopCloseBehavior"],
                  })
                }
              >
                <option value="tray">Sistem tepsisine küçült</option>
                <option value="quit">Uygulamadan tamamen çık</option>
              </select>
            </label>
            <label className="settings-panel__radio">
              <input
                type="checkbox"
                checked={settings.desktopOpenAtLogin}
                onChange={(event) => update({ desktopOpenAtLogin: event.target.checked })}
              />
              Windows başladığında Nexus'u aç
            </label>
            <label className="settings-panel__radio">
              <input
                type="checkbox"
                checked={settings.desktopStartMinimized}
                disabled={!settings.desktopOpenAtLogin}
                onChange={(event) => update({ desktopStartMinimized: event.target.checked })}
              />
              Başlangıçta sistem tepsisinde aç
            </label>
            <label className="settings-panel__radio">
              <input
                type="checkbox"
                checked={settings.desktopOverlayEnabled}
                onChange={(event) => update({ desktopOverlayEnabled: event.target.checked })}
              />
              Mini ses penceresini etkinleştir
            </label>
            <div className="settings-panel__test-row">
              <button type="button" onClick={() => void desktopBridge.openOverlay()}>
                Mini pencereyi aç
              </button>
            </div>
          </div>
        ) : null}

        {tab === "advanced" ? (
          <div className="settings-panel__section">
            <h3 className="settings-panel__section-title">Masaüstü istemcisi</h3>
            <dl className="desktop-runtime-info">
              <div><dt>Runtime</dt><dd>Electron · {desktopBridge.platform}</dd></div>
              <div><dt>Sunucu</dt><dd>{desktopBridge.serverUrl}</dd></div>
              <div><dt>Güncelleme</dt><dd>{updateStatus.message}</dd></div>
            </dl>
            <label className="settings-panel__radio">
              <input
                type="checkbox"
                checked={settings.desktopAutoCheckUpdates}
                onChange={(event) => update({ desktopAutoCheckUpdates: event.target.checked })}
              />
              Açılışta güvenli güncelleme denetimi yap
            </label>
            <div className="settings-panel__test-row">
              <button
                type="button"
                disabled={updateStatus.state === "checking" || updateStatus.state === "downloading"}
                onClick={() => void desktopBridge.checkForUpdates().then(setUpdateStatus)}
              >
                Güncellemeleri denetle
              </button>
              {updateStatus.state === "downloaded" ? (
                <button type="button" onClick={() => void desktopBridge.installUpdate()}>
                  Yeniden başlat ve kur
                </button>
              ) : null}
            </div>
            <p className="settings-panel__hint">
              Production paketleri kod imzalı olmalı; istemci yalnız yayın metadata'sındaki
              doğrulanmış SHA-512 özetiyle eşleşen NSIS paketini kurar.
            </p>
          </div>
        ) : null}

        <div className="settings-panel__actions">
          <button onClick={handleReset}>Varsayılana dön</button>
          <button className="settings-panel__save" onClick={() => void handleSave()}>
            Kaydet
          </button>
        </div>
          </>
        )}
      </div>
    </div>
  );
}
