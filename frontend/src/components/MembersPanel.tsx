import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { ApiError, coreApi } from "../api/client";
import type { Member } from "../types";

interface MembersPanelProps {
  serverId: number;
  serverName: string;
  canInvite: boolean;
  onClose: () => void;
}

export function MembersPanel({ serverId, serverName, canInvite, onClose }: MembersPanelProps) {
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
              {members.map((member) => (
                <li key={member.id}>{member.display_name ?? member.username}</li>
              ))}
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
