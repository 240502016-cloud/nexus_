import { useState } from "react";
import { createPortal } from "react-dom";

import type { VoiceChannelState } from "../hooks/useVoiceChannel";
import { comboLabel } from "../settings";
import type { VoiceSettings } from "../settings";
import type { User } from "../types";
import { Icon } from "./Icon";
import { SoundboardPanel } from "./SoundboardPanel";

interface VoicePanelProps {
  voice: VoiceChannelState;
  currentUser: User;
  voiceSettings: VoiceSettings;
  onLeave: () => void;
}

/**
 * Aktif ses kanalının kontrol çubuğu (mute/deafen/kamera/ekran/ayrıl).
 * Katılımcı listesi artık tek kaynaktan (gateway roster'ı) sidebar'da gösterilir; burada
 * tekrar edilmez.
 */
export function VoicePanel({ voice, currentUser, voiceSettings, onLeave }: VoicePanelProps) {
  const [soundboardOpen, setSoundboardOpen] = useState(false);
  const {
    connected,
    muted,
    deafened,
    cameraEnabled,
    screenShareEnabled,
    screenAudioEnabled,
    error,
    toggleMute,
    toggleDeafen,
    toggleCamera,
    toggleScreenShare,
  } = voice;
  const isPtt = voiceSettings.mode === "ptt";

  return (
    <div className="voice-panel">
      {!connected && !error ? <div className="voice-panel__status">Bağlanıyor...</div> : null}
      {error ? <div className="voice-panel__error">{error}</div> : null}
      {isPtt ? (
        <div className="voice-panel__ptt-hint">
          Konuşmak için <strong>{comboLabel(voiceSettings.pttCombo)}</strong> tuşuna basılı tutun
        </div>
      ) : null}
      <div className="voice-panel__controls">
        <button
          className={muted ? "voice-ctrl voice-ctrl--danger" : "voice-ctrl"}
          onClick={toggleMute}
          title={muted ? "Susturmayı kaldır" : "Sustur"}
        >
          <Icon name={muted ? "micOff" : "mic"} />
          <span>{muted ? "Sesi aç" : "Sustur"}</span>
        </button>
        <button
          className={deafened ? "voice-ctrl voice-ctrl--danger" : "voice-ctrl"}
          onClick={toggleDeafen}
          title={deafened ? "Sağırlaştırmayı kaldır" : "Sağırlaştır"}
        >
          <Icon name={deafened ? "headphonesOff" : "headphones"} />
          <span>{deafened ? "Dinle" : "Sağırlaştır"}</span>
        </button>
        <button
          className={cameraEnabled ? "voice-ctrl voice-ctrl--active" : "voice-ctrl"}
          onClick={toggleCamera}
          title={cameraEnabled ? "Kamerayı kapat" : "Kamerayı aç"}
        >
          <Icon name="camera" />
          <span>Kamera</span>
        </button>
        <button
          className={screenShareEnabled ? "voice-ctrl voice-ctrl--active" : "voice-ctrl"}
          onClick={toggleScreenShare}
          title={screenShareEnabled
            ? (screenAudioEnabled ? "Ekran ve yayın sesini durdur" : "Ekran paylaşımını durdur")
            : "Ekran paylaş (sekme veya sistem sesi seçilebilir)"}
        >
          <Icon name="screen" />
          <span>Paylaş</span>
        </button>
        <button
          className={soundboardOpen ? "voice-ctrl voice-ctrl--active" : "voice-ctrl"}
          onClick={() => setSoundboardOpen((open) => !open)}
          title="Soundboard"
        >
          <Icon name="volume" />
          <span>Sesler</span>
        </button>
        <button className="voice-ctrl voice-ctrl--leave" onClick={onLeave} title="Kanaldan ayrıl">
          <Icon name="phone" />
          <span>Ayrıl</span>
        </button>
      </div>
      {screenShareEnabled && screenAudioEnabled ? (
        <div className="voice-panel__screen-audio">
          <div className="voice-panel__screen-audio-head">
            <Icon name="volume" />
            <span>Yayın sesi</span>
            <button
              type="button"
              className={voice.streamAudioMuted
                ? "voice-panel__screen-audio-toggle voice-panel__screen-audio-toggle--off"
                : "voice-panel__screen-audio-toggle"}
              onClick={voice.toggleStreamAudioMute}
              title={voice.streamAudioMuted
                ? "Yayın sesini tekrar gönder"
                : "Yayın sesini gönderme (mikrofon ve soundboard açık kalır)"}
            >
              {voice.streamAudioMuted ? "Kapalı" : "Açık"}
            </button>
          </div>
          <label className="voice-panel__screen-audio-level">
            <input
              type="range"
              min={0}
              max={200}
              step={10}
              value={voice.streamAudioVolume}
              disabled={voice.streamAudioMuted}
              aria-label="Yayın sesi seviyesi"
              onChange={(event) => voice.setStreamAudioVolume(Number(event.target.value))}
            />
            <span>%{voice.streamAudioVolume}</span>
          </label>
          <p className="voice-panel__screen-audio-note">
            Yalnız paylaştığın ekranın sesini etkiler; mikrofonun ve soundboard'ın ayrıdır.
          </p>
        </div>
      ) : null}
      <div className={`voice-panel__quality voice-panel__quality--${voice.connectionQuality.level}`}>
        <span />
        {voice.connectionQuality.level === "good"
          ? "Bağlantı iyi"
          : voice.connectionQuality.level === "fair"
            ? "Bağlantı orta"
            : voice.connectionQuality.level === "poor"
              ? "Bağlantı zayıf"
              : "Ölçülüyor"}
        {voice.connectionQuality.pingMs !== null ? ` · ${voice.connectionQuality.pingMs} ms` : ""}
        {voice.connectionQuality.packetLossPercent !== null
          ? ` · %${voice.connectionQuality.packetLossPercent} kayıp`
          : ""}
      </div>
      {soundboardOpen
        ? createPortal(
            <SoundboardPanel
              voice={voice}
              currentUserId={currentUser.id}
              onClose={() => setSoundboardOpen(false)}
            />,
            document.body,
          )
        : null}
    </div>
  );
}
