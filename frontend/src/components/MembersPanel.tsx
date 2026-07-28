import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { ApiError, coreApi } from "../api/client";
import type { PresenceInfo } from "../hooks/useGateway";
import type { Friend, Member } from "../types";
import { Icon } from "./Icon";

interface MembersPanelProps {
  serverId: number;
  serverName: string;
  canInvite: boolean;
  currentUserId: number;
  presences?: Map<number, PresenceInfo>;
  onCallMember?: (userId: number, username: string) => void;
  onInviteSent?: () => void;
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
  onInviteSent,
  onClose,
}: MembersPanelProps) {
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [friends, setFriends] = useState<Friend[]>([]);
  const [selectedFriendId, setSelectedFriendId] = useState("");
  const [inviting, setInviting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [inviteOpen, setInviteOpen] = useState(false);

  function loadMembers() {
    setLoading(true);
    coreApi
      .listMembers(serverId)
      .then(setMembers)
      .finally(() => setLoading(false));
  }

  useEffect(loadMembers, [serverId]);

  useEffect(() => {
    if (!inviteOpen) return;
    Promise.all([coreApi.listFriends(), coreApi.listServerInvites()])
      .then(([list, invites]) => {
        const pendingIds = new Set(
          invites.outgoing
            .filter((invite) => invite.server_id === serverId)
            .map((invite) => invite.invitee.id),
        );
        setFriends(
          list.filter(
            (friend) =>
              !members.some((member) => member.id === friend.user.id) &&
              !pendingIds.has(friend.user.id),
          ),
        );
      })
      .catch(() => setError("Arkadaş ve davet listesi yüklenemedi"));
  }, [inviteOpen, members, serverId]);

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
    const userId = Number(selectedFriendId);
    if (!userId) return;
    const friend = friends.find((item) => item.user.id === userId);

    setError(null);
    setNotice(null);
    setInviting(true);
    try {
      await coreApi.addMember(serverId, userId);
      setNotice(`${friend?.user.display_name || friend?.user.username || "Arkadaş"} kullanıcısına davet gönderildi.`);
      setSelectedFriendId("");
      setFriends((current) => current.filter((item) => item.user.id !== userId));
      onInviteSent?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Üye eklenemedi");
    } finally {
      setInviting(false);
    }
  }

  return (
    <aside className="members-dock" aria-label={`${serverName} üyeleri`}>
      <header className="members-dock__header">
        <div>
          <span>TOPLULUK</span>
          <strong>Üyeler · {members.length}</strong>
        </div>
        <button type="button" onClick={onClose} aria-label="Üye panelini kapat"><Icon name="close" /></button>
      </header>

      {loading ? (
        <div className="members-dock__loading">Üyeler yükleniyor…</div>
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
                <span className={`presence-dot presence-dot--${status}`} title={STATUS_LABEL[status]} />
                {member.avatar_url ? (
                  <img className="member-avatar" src={member.avatar_url} alt="" />
                ) : (
                  <span className="member-avatar member-avatar--empty">
                    {(member.display_name ?? member.username).charAt(0).toUpperCase()}
                  </span>
                )}
                <span className="members-panel__member-name">
                  <strong>{member.display_name ?? member.username}</strong>
                  <small>{custom || STATUS_LABEL[status] || "Çevrimdışı"}</small>
                </span>
                {!isSelf && onCallMember ? (
                  <button
                    className="members-panel__call"
                    title={online ? "Ses kanalına çağır" : "Çevrimdışı"}
                    disabled={!online}
                    onClick={() => onCallMember(member.id, member.username)}
                  >
                    <Icon name="phone" />
                  </button>
                ) : null}
                {canInvite && !isSelf ? (
                  <button
                    className="members-panel__kick"
                    title="Sunucudan çıkar"
                    onClick={() => handleKick(member.id, member.display_name ?? member.username)}
                  >
                    <Icon name="close" />
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}

      {canInvite ? (
        <div className="members-dock__invite">
          <button type="button" onClick={() => setInviteOpen((open) => !open)}>
            {inviteOpen ? "Davet formunu kapat" : "+ Arkadaşını davet et"}
          </button>
          {inviteOpen ? (
            <form onSubmit={handleInvite}>
              <select
                aria-label="Davet edilecek arkadaş"
                value={selectedFriendId}
                onChange={(event) => setSelectedFriendId(event.target.value)}
              >
                <option value="">Arkadaş seçin</option>
                {friends.map((friend) => (
                  <option key={friend.user.id} value={friend.user.id}>
                    {friend.user.display_name || friend.user.username}
                  </option>
                ))}
              </select>
              <button type="submit" disabled={inviting || !selectedFriendId}>
                {inviting ? "Gönderiliyor…" : "Davet gönder"}
              </button>
            </form>
          ) : null}
          {inviteOpen && friends.length === 0 ? (
            <small className="members-dock__invite-hint">
              Davet edilebilecek bir arkadaş yok. Önce profil ekranından arkadaş ekleyin.
            </small>
          ) : null}
          {error ? <div className="members-panel__error">{error}</div> : null}
          {notice ? <div className="members-panel__notice">{notice}</div> : null}
        </div>
      ) : null}
    </aside>
  );
}
