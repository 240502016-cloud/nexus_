import { useState } from "react";
import type { FormEvent } from "react";

import type { Server } from "../types";
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
