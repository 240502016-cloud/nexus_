import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { ApiError, coreApi } from "../api/client";
import type { PresenceInfo } from "../hooks/useGateway";
import type { Member } from "../types";

interface MembersPanelProps {
  serverId: number;
  serverName: string;
  canInvite: boolean;
  currentUserId: number;
  presences?: Map<number, PresenceInfo>;
  onCallMember?: (userId: number, username: string) => void;
  onClose: () => void;
}

const STATUS_LABEL: Record<string, string> = {
  online: "Çevrimiçi",
  idle: "Boşta",
  dnd: "Rahatsız etmeyin",
  offline: "Çevrimdışı",
};

export function MembersPanel({
  serverId,
  serverName,
  canInvite,
  currentUserId,
  presences,
  onCallMember,
  onClose,
}: MembersPanelProps) {
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [username, setUsername] = useState("");
  const [inviting, setInviting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function loadMembers() {
    setLoading(true);
    coreApi
      .listMembers(serverId)
      .then(setMembers)
      .finally(() => setLoading(false));
  }

  useEffect(loadMembers, [serverId]);

  async function handleKick(userId: number, name: string) {
    if (!window.confirm(`${name} sunucudan çıkarılsın mı?`)) return;
    setError(null);
    try {
      await coreApi.removeMember(serverId, userId);
      loadMembers();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Üye çıkarılamadı");
    }
  }

  async function handleInvite(event: FormEvent) {
    event.preventDefault();
    const trimmed = username.trim();
    if (!trimmed) return;

    setError(null);
    setNotice(null);
    setInviting(true);
    try {
      await coreApi.addMember(serverId, trimmed);
      setNotice(`${trimmed} sunucuya eklendi.`);
      setUsername("");
      loadMembers();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Üye eklenemedi");
    } finally {
      setInviting(false);
    }
  }

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-panel" onClick={(event) => event.stopPropagation()}>
        <header className="settings-panel__header">
          <h2>{serverName} — Üyeler</h2>
          <button className="settings-panel__close" onClick={onClose} aria-label="Kapat">
            ✕
          </button>
        </header>

        <div className="settings-panel__section">
          {loading ? (
            <div>Yükleniyor...</div>
          ) : (
            <ul className="members-panel__list">
              {members.map((member) => {
                const presence = presences?.get(member.id);
                const online = presence?.online ?? false;
                const status = online ? (presence?.status ?? "online") : "offline";
                const custom = online ? (presence?.custom ?? "") : "";
                const isSelf = member.id === currentUserId;
                return (
                  <li key={member.id} className="members-panel__row">
                    <span
                      className={`presence-dot presence-dot--${status}`}
                      title={STATUS_LABEL[status] ?? "Çevrimdışı"}
                    />
                    {member.avatar_url ? (
                      <img className="member-avatar" src={member.avatar_url} alt="" />
                    ) : (
                      <span className="member-avatar member-avatar--empty">
                        {(member.display_name ?? member.username).charAt(0).toUpperCase()}
                      </span>
                    )}
                    <span className="members-panel__member-name">
                      {member.display_name ?? member.username}
                      {custom ? <span className="members-panel__custom"> — {custom}</span> : null}
                    </span>
                    {!isSelf && onCallMember ? (
                      <button
                        className="members-panel__call"
                        title={online ? "Ses kanalına çağır" : "Çevrimdışı"}
                        disabled={!online}
                        onClick={() => onCallMember(member.id, member.username)}
                      >
                        📞
                      </button>
                    ) : null}
                    {canInvite && !isSelf ? (
                      <button
                        className="members-panel__kick"
                        title="Sunucudan çıkar"
                        onClick={() => handleKick(member.id, member.display_name ?? member.username)}
                      >
                        🚫
                      </button>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {canInvite ? (
          <form className="settings-panel__section" onSubmit={handleInvite}>
            <label htmlFor="invite-username">Kullanıcı adıyla davet et</label>
            <input
              id="invite-username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="kullanici-adi"
            />
            {error ? <div className="members-panel__error">{error}</div> : null}
            {notice ? <div className="members-panel__notice">{notice}</div> : null}
            <button type="submit" disabled={inviting || !username.trim()}>
              {inviting ? "Ekleniyor..." : "Davet et"}
            </button>
          </form>
        ) : null}
      </div>
    </div>
  );
}
