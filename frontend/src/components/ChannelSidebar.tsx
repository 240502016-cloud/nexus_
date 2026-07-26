import { useState } from "react";
import type { FormEvent } from "react";

import type { PresenceInfo, VoiceRosterMember } from "../hooks/useGateway";
import type { VoiceChannelState } from "../hooks/useVoiceChannel";
import type { VoiceSettings } from "../settings";
import type { Channel, ChannelType, Server, User } from "../types";
import { BotsPanel } from "./BotsPanel";
import { MembersPanel } from "./MembersPanel";
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
  onRenameServer?: (serverId: number) => void;
  onDeleteServer?: (serverId: number) => void;
  onLeaveServer?: (serverId: number) => void;
  presences?: Map<number, PresenceInfo>;
  voiceStates?: Map<number, VoiceRosterMember[]>;
  onCallMember?: (userId: number, username: string) => void;
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
            {m.deafened ? (
              <span title="Sağır">🎧⃠</span>
            ) : m.muted ? (
              <span title="Susturulmuş">🔇</span>
            ) : null}
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
  onRenameServer,
  onDeleteServer,
  onLeaveServer,
  presences,
  voiceStates,
  onCallMember,
}: ChannelSidebarProps) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [type, setType] = useState<ChannelType>("text");
  const [membersOpen, setMembersOpen] = useState(false);
  const [botsOpen, setBotsOpen] = useState(false);

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
            <button
              className="channel-sidebar__members-button"
              onClick={() => setMembersOpen(true)}
              title="Üyeler"
            >
              👥
            </button>
            <button
              className="channel-sidebar__members-button"
              onClick={() => setBotsOpen(true)}
              title="Botlar"
            >
              🤖
            </button>
            {canCreateChannel ? (
              <>
                <button
                  className="channel-sidebar__members-button"
                  onClick={() => onRenameServer?.(server.id)}
                  title="Sunucuyu yeniden adlandır"
                >
                  ✏️
                </button>
                <button
                  className="channel-sidebar__members-button"
                  onClick={() => onDeleteServer?.(server.id)}
                  title="Sunucuyu sil"
                >
                  🗑️
                </button>
              </>
            ) : (
              <button
                className="channel-sidebar__members-button"
                onClick={() => onLeaveServer?.(server.id)}
                title="Sunucudan ayrıl"
              >
                🚪
              </button>
            )}
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
                  <span className="channel-item__icon">{isVoice ? "🔊" : "#"}</span>
                  {channel.name}
                </button>
                {canCreateChannel ? (
                  <span className="channel-row__actions">
                    <button
                      className="channel-row__action"
                      title="Yeniden adlandır"
                      onClick={() => onRenameChannel?.(channel.id)}
                    >
                      ✏️
                    </button>
                    <button
                      className="channel-row__action"
                      title="Kanalı sil"
                      onClick={() => onDeleteChannel?.(channel.id)}
                    >
                      🗑️
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
                🔊 Ses
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

      {server && membersOpen ? (
        <MembersPanel
          serverId={server.id}
          serverName={server.name}
          canInvite={canCreateChannel}
          currentUserId={currentUser.id}
          presences={presences}
          onCallMember={onCallMember}
          onClose={() => setMembersOpen(false)}
        />
      ) : null}

      {server && botsOpen ? (
        <BotsPanel
          serverId={server.id}
          serverName={server.name}
          canManageBots={canCreateChannel}
          onClose={() => setBotsOpen(false)}
        />
      ) : null}
    </aside>
  );
}
