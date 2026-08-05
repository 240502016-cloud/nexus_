import { useState } from "react";
import type { FormEvent } from "react";

import type { VoiceRosterMember } from "../hooks/useGateway";
import { DEFAULT_PEER_AUDIO_PREFS } from "../hooks/useVoiceChannel";
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

/**
 * Bir yayıncının tek bir ses kaynağı için kaydırıcı.
 *
 * Mikrofon, soundboard ve yayın sesi tek WebRTC audio track'inde karışmış geldiği için
 * bu tercih yerelde uygulanamaz; signaling ile yayıncıya iletilir ve yayıncı bu dinleyiciye
 * özel bir miks üretir. Bu yüzden etki birkaç yüz milisaniye gecikmeyle görülür.
 */
function SourceSlider({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="voice-source" title={hint}>
      <span className="voice-source__label">{label}</span>
      <input
        type="range"
        min={0}
        max={200}
        step={10}
        value={value}
        aria-label={`${label} seviyesi`}
        onChange={(event) => onChange(Number(event.target.value))}
      />
      <span className="voice-source__value">%{value}</span>
    </label>
  );
}

function VoiceRosterMemberRow({
  member,
  adjustable,
  voice,
}: {
  member: VoiceRosterMember;
  adjustable: boolean;
  voice: VoiceChannelState;
}) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const volume = voice.remoteVolumes.get(member.user_id) ?? 100;
  const prefs = voice.peerAudioPrefs.get(member.user_id) ?? DEFAULT_PEER_AUDIO_PREFS;
  const customized =
    prefs.voice !== 100 || prefs.soundboard !== 100 || prefs.stream !== 100;

  return (
    <li
      className={adjustable
        ? "voice-roster__member voice-roster__member--adjustable"
        : "voice-roster__member"}
    >
      <span className="voice-roster__identity">
        {member.avatar_url ? (
          <img
            className={member.speaking ? "voice-avatar voice-avatar--speaking" : "voice-avatar"}
            src={member.avatar_url}
            alt=""
          />
        ) : (
          <span className={member.speaking ? "voice-avatar voice-avatar--speaking" : "voice-avatar"}>
            {memberInitial(member.username)}
          </span>
        )}
        <span className="voice-roster__name">{member.username}</span>
        <span className="voice-roster__icons">
          {member.muted ? <span title="Susturulmuş"><Icon name="micOff" /></span> : null}
          {member.deafened ? <span title="Sağır"><Icon name="headphonesOff" /></span> : null}
        </span>
      </span>
      {adjustable ? (
        <>
          <div className="voice-roster__controls">
            <label className="voice-roster__volume" title="Bu kişinin toplam sesi. Yalnız sende geçerlidir.">
              <Icon name="volume" />
              <input
                type="range"
                min={0}
                max={100}
                step={5}
                value={volume}
                aria-label={`${member.username} ses seviyesi`}
                onChange={(event) =>
                  voice.setRemoteVolume(member.user_id, Number(event.target.value))
                }
              />
              <span>%{volume}</span>
            </label>
            <button
              type="button"
              className={sourcesOpen || customized
                ? "voice-roster__sources-toggle voice-roster__sources-toggle--active"
                : "voice-roster__sources-toggle"}
              aria-expanded={sourcesOpen}
              onClick={() => setSourcesOpen((open) => !open)}
              title="Konuşma, soundboard ve yayın sesini ayrı ayrı ayarla"
            >
              <Icon name="sliders" />
            </button>
          </div>
          {sourcesOpen ? (
            <div className="voice-roster__sources">
              <SourceSlider
                label="Konuşma"
                hint="Yalnız mikrofon sesi"
                value={prefs.voice}
                onChange={(value) => voice.setPeerSourceVolume(member.user_id, "voice", value)}
              />
              <SourceSlider
                label="Soundboard"
                hint="Yalnız bu kişinin soundboard efektleri"
                value={prefs.soundboard}
                onChange={(value) => voice.setPeerSourceVolume(member.user_id, "soundboard", value)}
              />
              <SourceSlider
                label="Yayın sesi"
                hint="Yalnız paylaştığı ekranın/sekmenin sesi"
                value={prefs.stream}
                onChange={(value) => voice.setPeerSourceVolume(member.user_id, "stream", value)}
              />
              <p className="voice-roster__sources-note">
                Bu üç ayar yayıncıya iletilir ve yalnız senin duyduğun miksi değiştirir.
              </p>
            </div>
          ) : null}
        </>
      ) : null}
    </li>
  );
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
      {members.map((m) => (
        <VoiceRosterMemberRow
          key={m.user_id}
          member={m}
          adjustable={active && voice.connected && m.user_id !== currentUserId}
          voice={voice}
        />
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
