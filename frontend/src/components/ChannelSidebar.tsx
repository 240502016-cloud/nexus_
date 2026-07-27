import { useState } from "react";
import type { FormEvent } from "react";

import type { VoiceRosterMember } from "../hooks/useGateway";
import type { VoiceChannelState } from "../hooks/useVoiceChannel";
import type { VoiceSettings } from "../settings";
import type { Channel, ChannelType, Server, User } from "../types";
import { Icon } from "./Icon";
import { VoicePanel } from "./VoicePanel";

interface ChannelSidebarProps {
  server: Server | undefined;
  channels: Channel[];
  activeChannelId: number | null;
  onSelect: (channelId: number) => void;
  activeVoiceChannelId: number | null;
  onToggleVoice: (channelId: number) => void;
  currentUser: User;
  voiceSettings: VoiceSettings;
  voice: VoiceChannelState;
  canCreateChannel: boolean;
  onCreateChannel: (name: string, type: ChannelType) => Promise<void>;
  onRenameChannel?: (channelId: number) => void;
  onDeleteChannel?: (channelId: number) => void;
  onOpenServerSettings: () => void;
  voiceStates?: Map<number, VoiceRosterMember[]>;
  onOpenProfile: () => void;
  onOpenSettings: () => void;
}

function memberInitial(name: string): string {
  return name.trim().charAt(0).toUpperCase() || "?";
}

function VoiceRoster({ members }: { members: VoiceRosterMember[] }) {
  if (members.length === 0) return null;
  return (
    <ul className="voice-roster">
      {members.map((m) => (
        <li key={m.user_id} className="voice-roster__member">
          {m.avatar_url ? (
            <img
              className={m.speaking ? "voice-avatar voice-avatar--speaking" : "voice-avatar"}
              src={m.avatar_url}
              alt=""
            />
          ) : (
            <span className={m.speaking ? "voice-avatar voice-avatar--speaking" : "voice-avatar"}>
              {memberInitial(m.username)}
            </span>
          )}
          <span className="voice-roster__name">{m.username}</span>
          <span className="voice-roster__icons">
            {m.muted ? <span title="Susturulmuş"><Icon name="micOff" /></span> : null}
            {m.deafened ? <span title="Sağır"><Icon name="headphonesOff" /></span> : null}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function ChannelSidebar({
  server,
  channels,
  activeChannelId,
  onSelect,
  activeVoiceChannelId,
  onToggleVoice,
  currentUser,
  voiceSettings,
  voice,
  canCreateChannel,
  onCreateChannel,
  onRenameChannel,
  onDeleteChannel,
  onOpenServerSettings,
  voiceStates,
  onOpenProfile,
  onOpenSettings,
}: ChannelSidebarProps) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [type, setType] = useState<ChannelType>("text");

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    await onCreateChannel(name.trim(), type);
    setName("");
    setType("text");
    setCreating(false);
  }

  return (
    <aside className="channel-sidebar">
      <header className="channel-sidebar__header">
        <span>{server?.name ?? "Sunucu seçin"}</span>
        {server ? (
          <span className="channel-sidebar__header-actions">
            <button className="channel-sidebar__members-button" onClick={onOpenServerSettings} title="Sunucu ayarları">
              <Icon name="settings" />
            </button>
          </span>
        ) : null}
      </header>
      <ul className="channel-list">
        {channels.map((channel) => {
          const isVoice = channel.type === "voice";
          const isActiveVoice = isVoice && channel.id === activeVoiceChannelId;
          return (
            <li key={channel.id}>
              <div className="channel-row">
                <button
                  className={
                    (!isVoice && channel.id === activeChannelId) || isActiveVoice
                      ? "channel-item active"
                      : "channel-item"
                  }
                  onClick={() => (isVoice ? onToggleVoice(channel.id) : onSelect(channel.id))}
                >
                  <span className="channel-item__icon"><Icon name={isVoice ? "volume" : "hash"} /></span>
                  {channel.name}
                </button>
                {canCreateChannel ? (
                  <span className="channel-row__actions">
                    <button
                      className="channel-row__action"
                      title="Yeniden adlandır"
                      onClick={() => onRenameChannel?.(channel.id)}
                    >
                      <Icon name="edit" />
                    </button>
                    <button
                      className="channel-row__action"
                      title="Kanalı sil"
                      onClick={() => onDeleteChannel?.(channel.id)}
                    >
                      <Icon name="trash" />
                    </button>
                  </span>
                ) : null}
              </div>
              {isVoice ? <VoiceRoster members={voiceStates?.get(channel.id) ?? []} /> : null}
              {isActiveVoice ? (
                <VoicePanel
                  voice={voice}
                  currentUser={currentUser}
                  voiceSettings={voiceSettings}
                  onLeave={() => onToggleVoice(channel.id)}
                />
              ) : null}
            </li>
          );
        })}
      </ul>

      {server && canCreateChannel ? (
        creating ? (
          <form className="channel-sidebar__create-form" onSubmit={handleCreate}>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="kanal-adı"
              autoFocus
            />
            <div className="channel-sidebar__create-type">
              <label>
                <input
                  type="radio"
                  checked={type === "text"}
                  onChange={() => setType("text")}
                />
                # Metin
              </label>
              <label>
                <input
                  type="radio"
                  checked={type === "voice"}
                  onChange={() => setType("voice")}
                />
                <Icon name="volume" /> Ses
              </label>
            </div>
            <div className="channel-sidebar__create-actions">
              <button type="submit">Oluştur</button>
              <button type="button" onClick={() => setCreating(false)}>
                Vazgeç
              </button>
            </div>
          </form>
        ) : (
          <button className="channel-sidebar__create-button" onClick={() => setCreating(true)}>
            + Kanal oluştur
          </button>
        )
      ) : null}

      <div className="user-dock">
        {currentUser.avatar_url ? (
          <img className="user-dock__avatar" src={currentUser.avatar_url} alt="" />
        ) : (
          <span className="user-dock__avatar user-dock__avatar--empty">
            {memberInitial(currentUser.display_name || currentUser.username)}
          </span>
        )}
        <button type="button" className="user-dock__identity" onClick={onOpenProfile} title="Profili aç">
          <strong>{currentUser.display_name || currentUser.username}</strong>
          <span>@{currentUser.username}</span>
        </button>
        <button type="button" className="user-dock__action" onClick={onOpenSettings} title="Ayarlar">
          <Icon name="settings" />
        </button>
      </div>

    </aside>
  );
}
