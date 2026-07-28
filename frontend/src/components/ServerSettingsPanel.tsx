import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { ApiError, coreApi } from "../api/client";
import { desktopBridge } from "../desktopBridge";
import type { Server, ServerJoinCode } from "../types";
import { BotsPanel } from "./BotsPanel";
import { Icon } from "./Icon";

export function ServerSettingsPanel({
  server,
  canManage,
  onClose,
  onSave,
  onDelete,
  onLeave,
}: {
  server: Server;
  canManage: boolean;
  onClose: () => void;
  onSave: (patch: { name: string; description: string | null }) => Promise<void>;
  onDelete: () => void;
  onLeave: () => void;
}) {
  const [tab, setTab] = useState<"general" | "bots">("general");
  const [name, setName] = useState(server.name);
  const [description, setDescription] = useState(server.description ?? "");
  const [saving, setSaving] = useState(false);
  const [joinCode, setJoinCode] = useState<ServerJoinCode | null>(null);
  const [joinCodeBusy, setJoinCodeBusy] = useState(false);
  const [joinCodeNotice, setJoinCodeNotice] = useState<string | null>(null);
  const [joinCodeError, setJoinCodeError] = useState<string | null>(null);

  useEffect(() => {
    if (!canManage) return;
    let cancelled = false;
    coreApi
      .getServerJoinCode(server.id)
      .then((record) => {
        if (!cancelled) setJoinCode(record);
      })
      .catch((error) => {
        if (!cancelled && (!(error instanceof ApiError) || error.status !== 404)) {
          setJoinCodeError(error instanceof Error ? error.message : "Davet kodu yüklenemedi");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [canManage, server.id]);

  function inviteLink(record: ServerJoinCode): string {
    const base = (desktopBridge.serverUrl ?? window.location.origin).replace(/\/+$/, "");
    return `${base}/?invite=${encodeURIComponent(record.code)}`;
  }

  async function createJoinCode() {
    setJoinCodeBusy(true);
    setJoinCodeError(null);
    try {
      setJoinCode(await coreApi.createServerJoinCode(server.id));
    } catch (error) {
      setJoinCodeError(error instanceof Error ? error.message : "Davet kodu oluşturulamadı");
    } finally {
      setJoinCodeBusy(false);
    }
  }

  async function rotateJoinCode() {
    if (!window.confirm("Eski davet bağlantısı hemen geçersiz olacak. Yeni kod oluşturulsun mu?")) return;
    setJoinCodeBusy(true);
    setJoinCodeError(null);
    try {
      setJoinCode(await coreApi.rotateServerJoinCode(server.id));
      setJoinCodeNotice("Yeni davet kodu oluşturuldu; eski bağlantı artık geçersiz.");
    } catch (error) {
      setJoinCodeError(error instanceof Error ? error.message : "Davet kodu yenilenemedi");
    } finally {
      setJoinCodeBusy(false);
    }
  }

  async function revokeJoinCode() {
    if (!window.confirm("Paylaşılabilir davet bağlantısı iptal edilsin mi?")) return;
    setJoinCodeBusy(true);
    setJoinCodeError(null);
    try {
      await coreApi.revokeServerJoinCode(server.id);
      setJoinCode(null);
      setJoinCodeNotice("Davet bağlantısı iptal edildi.");
    } catch (error) {
      setJoinCodeError(error instanceof Error ? error.message : "Davet bağlantısı iptal edilemedi");
    } finally {
      setJoinCodeBusy(false);
    }
  }

  async function copyJoinLink() {
    if (!joinCode) return;
    try {
      await navigator.clipboard.writeText(inviteLink(joinCode));
      setJoinCodeNotice("Davet bağlantısı panoya kopyalandı.");
    } catch {
      setJoinCodeError("Panoya kopyalanamadı; bağlantıyı elle seçip kopyalayın.");
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    try {
      await onSave({ name: name.trim(), description: description.trim() || null });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-panel settings-panel--wide server-settings" onClick={(event) => event.stopPropagation()}>
        <header className="settings-panel__header">
          <div><span className="panel-eyebrow">SUNUCU YÖNETİMİ</span><h2>{server.name}</h2></div>
          <button className="settings-panel__close" onClick={onClose}><Icon name="close" /></button>
        </header>
        <nav className="settings-panel__tabs">
          <button className={tab === "general" ? "settings-panel__tab active" : "settings-panel__tab"} onClick={() => setTab("general")}><Icon name="settings" /> Genel</button>
          <button className={tab === "bots" ? "settings-panel__tab active" : "settings-panel__tab"} onClick={() => setTab("bots")}><Icon name="bot" /> Botlar</button>
        </nav>
        {tab === "general" ? (
          <form className="settings-panel__section server-settings__form" onSubmit={save}>
            <label className="settings-panel__field"><span>Sunucu adı</span><input value={name} onChange={(event) => setName(event.target.value)} disabled={!canManage} /></label>
            <label className="settings-panel__field"><span>Açıklama</span><textarea rows={4} value={description} onChange={(event) => setDescription(event.target.value)} disabled={!canManage} /></label>
            {canManage ? <button className="settings-panel__save" disabled={saving}>{saving ? "Kaydediliyor…" : "Değişiklikleri kaydet"}</button> : null}
            {canManage ? (
              <section className="server-join-code">
                <div>
                  <strong>Arkadaşlık gerektirmeyen davet</strong>
                  <p>Bu bağlantıya sahip kullanıcılar doğrudan sunucuya ve ses kanallarına katılabilir.</p>
                </div>
                {joinCode ? (
                  <>
                    <label>
                      <span>Davet bağlantısı</span>
                      <input value={inviteLink(joinCode)} readOnly onFocus={(event) => event.currentTarget.select()} />
                    </label>
                    <code>{joinCode.code}</code>
                    <div className="server-join-code__actions">
                      <button type="button" onClick={() => void copyJoinLink()} disabled={joinCodeBusy}>Bağlantıyı kopyala</button>
                      <button type="button" onClick={() => void rotateJoinCode()} disabled={joinCodeBusy}>Kodu yenile</button>
                      <button type="button" className="danger" onClick={() => void revokeJoinCode()} disabled={joinCodeBusy}>İptal et</button>
                    </div>
                  </>
                ) : (
                  <button type="button" onClick={() => void createJoinCode()} disabled={joinCodeBusy}>
                    {joinCodeBusy ? "Oluşturuluyor…" : "Paylaşılabilir davet oluştur"}
                  </button>
                )}
                {joinCodeNotice ? <small className="settings-panel__ok-text">{joinCodeNotice}</small> : null}
                {joinCodeError ? <small className="profile-panel__alert profile-panel__alert--error">{joinCodeError}</small> : null}
              </section>
            ) : null}
            <div className="server-settings__danger">
              <strong>{canManage ? "Tehlikeli alan" : "Sunucudan ayrıl"}</strong>
              <p>{canManage ? "Sunucuyu silmek tüm kanalları kalıcı olarak kaldırır." : "Daha sonra yeniden davet edilmeniz gerekir."}</p>
              <button type="button" onClick={canManage ? onDelete : onLeave}>{canManage ? "Sunucuyu sil" : "Sunucudan ayrıl"}</button>
            </div>
          </form>
        ) : (
          <BotsPanel serverId={server.id} serverName={server.name} canManageBots={canManage} onClose={onClose} embedded />
        )}
      </div>
    </div>
  );
}
