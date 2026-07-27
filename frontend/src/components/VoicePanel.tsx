import type { VoiceChannelState } from "../hooks/useVoiceChannel";
import { comboLabel } from "../settings";
import type { VoiceSettings } from "../settings";
import type { User } from "../types";
import { Icon } from "./Icon";

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
export function VoicePanel({ voice, voiceSettings, onLeave }: VoicePanelProps) {
  const {
    connected,
    muted,
    deafened,
    cameraEnabled,
    screenShareEnabled,
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
        </button>
        <button
          className={deafened ? "voice-ctrl voice-ctrl--danger" : "voice-ctrl"}
          onClick={toggleDeafen}
          title={deafened ? "Sağırlaştırmayı kaldır" : "Sağırlaştır"}
        >
          <Icon name={deafened ? "headphonesOff" : "headphones"} />
        </button>
        <button
          className={cameraEnabled ? "voice-ctrl voice-ctrl--active" : "voice-ctrl"}
          onClick={toggleCamera}
          title={cameraEnabled ? "Kamerayı kapat" : "Kamerayı aç"}
        >
          <Icon name="camera" />
        </button>
        <button
          className={screenShareEnabled ? "voice-ctrl voice-ctrl--active" : "voice-ctrl"}
          onClick={toggleScreenShare}
          title={screenShareEnabled ? "Ekran paylaşımını durdur" : "Ekran paylaş"}
        >
          <Icon name="screen" />
        </button>
        <button className="voice-ctrl voice-ctrl--leave" onClick={onLeave} title="Kanaldan ayrıl">
          <Icon name="phone" />
        </button>
      </div>
    </div>
  );
}
