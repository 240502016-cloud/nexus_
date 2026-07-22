import { useState } from "react";
import type { FormEvent } from "react";

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
  canCreateChannel: boolean;
  onCreateChannel: (name: string, type: ChannelType) => Promise<void>;
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
  canCreateChannel,
  onCreateChannel,
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
          </span>
        ) : null}
      </header>
      <ul className="channel-list">
        {channels.map((channel) => {
          const isVoice = channel.type === "voice";
          const isActiveVoice = isVoice && channel.id === activeVoiceChannelId;
          return (
            <li key={channel.id}>
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
              {isActiveVoice ? (
                <VoicePanel
                  channelId={channel.id}
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
