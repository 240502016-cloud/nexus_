import { useVoiceChannel } from "../hooks/useVoiceChannel";
import { comboLabel } from "../settings";
import type { VoiceSettings } from "../settings";
import type { User } from "../types";

interface VoicePanelProps {
  channelId: number;
  currentUser: User;
  voiceSettings: VoiceSettings;
  onLeave: () => void;
}

function statusIcon(muted: boolean, speaking: boolean): string {
  if (muted) return "🔴";
  if (speaking) return "🟢";
  return "⚪";
}

export function VoicePanel({ channelId, currentUser, voiceSettings, onLeave }: VoicePanelProps) {
  const { connected, participants, muted, error, toggleMute, disconnect } = useVoiceChannel(
    channelId,
    voiceSettings,
  );
  const isPtt = voiceSettings.mode === "ptt";

  function handleLeave() {
    disconnect();
    onLeave();
  }

  return (
    <div className="voice-panel">
      {!connected && !error ? <div className="voice-panel__status">Bağlanıyor...</div> : null}
      {error ? <div className="voice-panel__error">{error}</div> : null}
      <ul className="voice-panel__participants">
        <li className="voice-panel__participant">
          <span>{statusIcon(muted, false)}</span>
          <span>{currentUser.username} (sen)</span>
        </li>
        {participants.map((participant) => (
          <li key={participant.user_id} className="voice-panel__participant">
            <span>{statusIcon(participant.muted, participant.speaking)}</span>
            <span>{participant.username}</span>
          </li>
        ))}
      </ul>
      {isPtt ? (
        <div className="voice-panel__ptt-hint">
          Konuşmak için <strong>{comboLabel(voiceSettings.pttCombo)}</strong> tuşuna basılı tutun
        </div>
      ) : null}
      <div className="voice-panel__controls">
        {isPtt ? null : <button onClick={toggleMute}>{muted ? "Sesi Aç" : "Sustur"}</button>}
        <button onClick={handleLeave}>Ayrıl</button>
      </div>
    </div>
  );
}
