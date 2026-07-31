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
  pendingFriendRequestCount: number;
  onOpenProfile: () => void;
  onOpenSettings: () => void;
  unreadCounts: Map<number, number>;
}

function memberInitial(name: string): string {
  return name.trim().charAt(0).toUpperCase() || "?";
}

function VoiceRoster({
  members,
  active,
  currentUserId,
  voice,
}: {
  members: VoiceRosterMember[];
  active: boolean;
  currentUserId: number;
  voice: VoiceChannelState;
}) {
  if (members.length === 0) return null;
  return (
    <ul className="voice-roster">
      {members.map((m) => {
        const adjustable = active && voice.connected && m.user_id !== currentUserId;
        const volume = voice.remoteVolumes.get(m.user_id) ?? 100;
        return (
          <li
            key={m.user_id}
            className={adjustable
              ? "voice-roster__member voice-roster__member--adjustable"
              : "voice-roster__member"}
          >
            <span className="voice-roster__identity">
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
            </span>
            {adjustable ? (
              <label className="voice-roster__volume" title="Bu ayar yalnızca sende geçerlidir">
                <Icon name="volume" />
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={volume}
                  aria-label={`${m.username} ses seviyesi`}
                  onChange={(event) => voice.setRemoteVolume(m.user_id, Number(event.target.value))}
                />
                <span>%{volume}</span>
              </label>
            ) : null}
          </li>
        );
      })}
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
  pendingFriendRequestCount,
  onOpenProfile,
  onOpenSettings,
  unreadCounts,
}: ChannelSidebarProps) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [type, setType] = useState<ChannelType>("text");
  const activeVoiceChannel = channels.find((channel) => channel.id === activeVoiceChannelId);

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
      <div className="channel-sidebar__body">
        <div className="channel-sidebar__section-heading">
          <span>Kanallar</span>
          {server && canCreateChannel && !creating ? (
            <button
              type="button"
              className="channel-sidebar__create-button"
              onClick={() => setCreating(true)}
              title="Kanal oluştur"
              aria-label="Kanal oluştur"
            >
              +
            </button>
          ) : null}
        </div>

        {server && canCreateChannel && creating ? (
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
        ) : null}

        <ul className="channel-list">
        {channels.map((channel) => {
          const isVoice = channel.type === "voice";
          const isActiveVoice = isVoice && channel.id === activeVoiceChannelId;
          const unreadCount = isVoice ? 0 : (unreadCounts.get(channel.id) ?? 0);
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
                  <span className="channel-item__label">{channel.name}</span>
                  {unreadCount > 0 ? (
                    <span className="channel-item__unread" aria-label={`${unreadCount} okunmamış mesaj`}>
                      {unreadCount > 99 ? "99+" : unreadCount}
                    </span>
                  ) : null}
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
              {isVoice ? (
                <VoiceRoster
                  members={voiceStates?.get(channel.id) ?? []}
                  active={isActiveVoice}
                  currentUserId={currentUser.id}
                  voice={voice}
                />
              ) : null}
            </li>
          );
        })}
        </ul>
      </div>

      {activeVoiceChannel ? (
        <section className="channel-sidebar__voice-module" aria-label="Aktif ses bağlantısı">
          <header>
            <span>Ses bağlantısı</span>
            <strong>{activeVoiceChannel.name}</strong>
          </header>
          <VoicePanel
            voice={voice}
            currentUser={currentUser}
            voiceSettings={voiceSettings}
            onLeave={() => onToggleVoice(activeVoiceChannel.id)}
          />
        </section>
      ) : null}

      <div className="user-dock">
        {currentUser.avatar_url ? (
          <img className="user-dock__avatar" src={currentUser.avatar_url} alt="" />
        ) : (
          <span className="user-dock__avatar user-dock__avatar--empty">
            {memberInitial(currentUser.display_name || currentUser.username)}
          </span>
        )}
        <button
          type="button"
          className="user-dock__identity"
          onClick={onOpenProfile}
          title={pendingFriendRequestCount ? `${pendingFriendRequestCount} arkadaşlık isteği` : "Profili aç"}
        >
          <strong>{currentUser.display_name || currentUser.username}</strong>
          <span>@{currentUser.username}</span>
          {pendingFriendRequestCount ? (
            <b className="user-dock__friend-badge" aria-label={`${pendingFriendRequestCount} bekleyen arkadaşlık isteği`}>
              {pendingFriendRequestCount > 9 ? "9+" : pendingFriendRequestCount}
            </b>
          ) : null}
        </button>
        <button type="button" className="user-dock__action" onClick={onOpenSettings} title="Ayarlar">
          <Icon name="settings" />
        </button>
      </div>

    </aside>
  );
}
