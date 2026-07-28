import { useState } from "react";

import { ApiError } from "../api/client";
import type { Server, ServerInviteList } from "../types";
import { Icon } from "./Icon";

interface ServerInvitesPanelProps {
  invites: ServerInviteList;
  loading: boolean;
  onAccept: (inviteId: number) => Promise<Server>;
  onDecline: (inviteId: number) => Promise<void>;
  onClose: () => void;
}

function initial(value: string): string {
  return value.trim().charAt(0).toUpperCase() || "N";
}

export function ServerInvitesPanel({
  invites,
  loading,
  onAccept,
  onDecline,
  onClose,
}: ServerInvitesPanelProps) {
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function accept(inviteId: number) {
    setBusyId(inviteId);
    setError(null);
    try {
      await onAccept(inviteId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Davet kabul edilemedi");
    } finally {
      setBusyId(null);
    }
  }

  async function decline(inviteId: number) {
    setBusyId(inviteId);
    setError(null);
    try {
      await onDecline(inviteId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Davet kaldırılamadı");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="server-invites-overlay" onClick={onClose}>
      <section className="server-invites-panel" onClick={(event) => event.stopPropagation()}>
        <header className="server-invites-panel__header">
          <div className="server-invites-panel__title-icon"><Icon name="inbox" /></div>
          <div>
            <span>DAVET KUTUSU</span>
            <h2>Sunucu davetleri</h2>
            <p>Katılmadan önce sunucuyu ve davet eden kişiyi kontrol edebilirsin.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Davetleri kapat"><Icon name="close" /></button>
        </header>

        {error ? <div className="server-invites-panel__error">{error}</div> : null}

        <div className="server-invites-panel__content">
          <section>
            <div className="server-invites-panel__section-title">
              <h3>Gelen davetler</h3>
              <span>{invites.incoming.length}</span>
            </div>
            {loading ? (
              <div className="server-invites-panel__empty">Davetler yükleniyor…</div>
            ) : invites.incoming.length ? (
              <div className="server-invite-list">
                {invites.incoming.map((invite) => (
                  <article className="server-invite-card" key={invite.id}>
                    {invite.server_icon_url ? (
                      <img src={invite.server_icon_url} alt="" />
                    ) : (
                      <div className="server-invite-card__avatar">{initial(invite.server_name)}</div>
                    )}
                    <div className="server-invite-card__body">
                      <small>SUNUCU DAVETİ</small>
                      <strong>{invite.server_name}</strong>
                      <span>
                        <b>{invite.inviter.display_name || invite.inviter.username}</b> seni davet etti
                      </span>
                    </div>
                    <div className="server-invite-card__actions">
                      <button
                        type="button"
                        className="server-invite-card__accept"
                        disabled={busyId !== null}
                        onClick={() => void accept(invite.id)}
                      >
                        {busyId === invite.id ? "Katılınıyor…" : "Kabul et"}
                      </button>
                      <button
                        type="button"
                        className="server-invite-card__decline"
                        disabled={busyId !== null}
                        onClick={() => void decline(invite.id)}
                      >
                        Reddet
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className="server-invites-panel__empty">
                <Icon name="inbox" />
                <strong>Bekleyen davet yok</strong>
                <span>Yeni bir davet geldiğinde burada ve sol menüde bir rozet göreceksin.</span>
              </div>
            )}
          </section>

          {invites.outgoing.length ? (
            <section>
              <div className="server-invites-panel__section-title">
                <h3>Gönderilen davetler</h3>
                <span>{invites.outgoing.length}</span>
              </div>
              <div className="server-invite-list server-invite-list--outgoing">
                {invites.outgoing.map((invite) => (
                  <article className="server-invite-card server-invite-card--compact" key={invite.id}>
                    <div className="server-invite-card__avatar">
                      {initial(invite.invitee.display_name || invite.invitee.username)}
                    </div>
                    <div className="server-invite-card__body">
                      <strong>{invite.invitee.display_name || invite.invitee.username}</strong>
                      <span>{invite.server_name} davetine yanıt bekleniyor</span>
                    </div>
                    <button
                      type="button"
                      className="server-invite-card__decline"
                      disabled={busyId !== null}
                      onClick={() => void decline(invite.id)}
                    >
                      İptal et
                    </button>
                  </article>
                ))}
              </div>
            </section>
          ) : null}
        </div>
      </section>
    </div>
  );
}
