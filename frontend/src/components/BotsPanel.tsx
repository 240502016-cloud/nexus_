import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { ApiError, coreApi } from "../api/client";
import type { Bot, PluginManifest } from "../types";
import { Icon } from "./Icon";

interface BotsPanelProps {
  serverId: number;
  serverName: string;
  canManageBots: boolean;
  onClose: () => void;
  embedded?: boolean;
}

export function BotsPanel({ serverId, serverName, canManageBots, onClose, embedded = false }: BotsPanelProps) {
  const [bots, setBots] = useState<Bot[]>([]);
  const [plugins, setPlugins] = useState<PluginManifest[]>([]);
  const [loading, setLoading] = useState(true);
  const [botName, setBotName] = useState("");
  const [selectedPluginName, setSelectedPluginName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pluginBusy, setPluginBusy] = useState<string | null>(null);
  const [botPluginBusy, setBotPluginBusy] = useState<string | null>(null);

  function loadAll() {
    setLoading(true);
    Promise.all([coreApi.listServerBots(serverId), coreApi.listPlugins()])
      .then(([serverBots, allPlugins]) => {
        setBots(serverBots);
        setPlugins(allPlugins);
      })
      .finally(() => setLoading(false));
  }

  useEffect(loadAll, [serverId]);

  async function handleCreateBot(event: FormEvent) {
    event.preventDefault();
    const trimmed = botName.trim();
    if (!trimmed) return;

    setError(null);
    setNotice(null);
    setCreating(true);
    try {
      const bot = await coreApi.createBot(trimmed);
      await coreApi.addBotToServer(bot.id, serverId);
      if (selectedPluginName) {
        await coreApi.linkPluginToBot(serverId, bot.id, selectedPluginName);
      }
      setNotice(
        selectedPluginName
          ? `${trimmed} botu oluşturuldu; ${selectedPluginName} bağlandı.`
          : `${trimmed} botu oluşturuldu ve sunucuya eklendi.`,
      );
      setBotName("");
      setSelectedPluginName("");
      loadAll();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Bot oluşturulamadı");
    } finally {
      setCreating(false);
    }
  }

  async function handleToggleBotPlugin(bot: Bot, plugin: PluginManifest) {
    const busyKey = `${bot.id}:${plugin.name}`;
    setBotPluginBusy(busyKey);
    setError(null);
    setNotice(null);
    try {
      if (bot.plugin_names.includes(plugin.name)) {
        await coreApi.unlinkPluginFromBot(serverId, bot.id, plugin.name);
        setNotice(`${plugin.name}, ${bot.name} botundan kaldırıldı.`);
      } else {
        await coreApi.linkPluginToBot(serverId, bot.id, plugin.name);
        setNotice(`${plugin.name}, ${bot.name} botuna bağlandı.`);
      }
      loadAll();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Bot plugin bağlantısı değiştirilemedi");
    } finally {
      setBotPluginBusy(null);
    }
  }

  const dedicatedPlugins = plugins.filter((plugin) => plugin.enabled && plugin.requires_bot_link);

  async function handleTogglePlugin(plugin: PluginManifest) {
    setPluginBusy(plugin.name);
    setError(null);
    try {
      if (plugin.enabled) {
        await coreApi.uninstallPlugin(plugin.name);
      } else {
        await coreApi.installPlugin(plugin.name);
      }
      loadAll();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Plugin işlemi başarısız");
    } finally {
      setPluginBusy(null);
    }
  }

  async function removeBot(bot: Bot) {
    if (!window.confirm(`${bot.name} bu sunucudan kaldırılsın mı?`)) return;
    setBotPluginBusy(`remove:${bot.id}`);
    try {
      await coreApi.removeBotFromServer(bot.id, serverId);
      setNotice(`${bot.name} sunucudan kaldırıldı.`);
      loadAll();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Bot kaldırılamadı");
    } finally {
      setBotPluginBusy(null);
    }
  }

  const body = (
    <>
      {!embedded ? (
        <header className="settings-panel__header">
          <h2>{serverName} — Botlar</h2>
          <button className="settings-panel__close" onClick={onClose} aria-label="Kapat">
            <Icon name="close" />
          </button>
        </header>
      ) : null}

      <div className="bots-panel__intro">
        <div className="bots-panel__intro-icon"><Icon name="bot" /></div>
        <div>
          <span className="panel-eyebrow">OTOMASYON MERKEZİ</span>
          <h3>Botlar ve platform eklentileri</h3>
          <p>Botları sunucuya ekleyin, yeteneklerini bağlayın ve kullanılabilir komutları tek ekrandan yönetin.</p>
        </div>
        <span className="bots-panel__summary">{bots.length} bot · {plugins.filter((plugin) => plugin.enabled).length} etkin</span>
      </div>

      {error ? <div className="members-panel__error bots-panel__feedback">{error}</div> : null}
      {notice ? <div className="members-panel__notice bots-panel__feedback">{notice}</div> : null}

      {loading ? (
        <div className="bots-panel__loading">Botlar ve eklentiler yükleniyor…</div>
      ) : (
        <div className="bots-panel__content">
          <section className="bots-panel__section">
            <header className="bots-panel__section-header">
              <div><span>SUNUCU BOTLARI</span><h3>Aktif botlar</h3></div>
              <b>{bots.length}</b>
            </header>
            {bots.length === 0 ? (
              <div className="bots-panel__empty"><Icon name="bot" /><span>Henüz bot eklenmemiş.</span></div>
            ) : (
              <ul className="bots-panel__bot-grid">
                {bots.map((bot) => (
                  <li key={bot.id} className="bots-panel__bot-card">
                    <div className="bots-panel__bot-identity">
                      <span className="bots-panel__bot-avatar"><Icon name="bot" /></span>
                      <div>
                        <strong>{bot.name}</strong>
                        <span>Komut öneki: <code>{bot.command_prefix}</code></span>
                      </div>
                    </div>
                    <div className="bots-panel__plugin-commands">
                      {bot.plugin_names.length > 0
                        ? bot.plugin_names.map((name) => <span key={name}>{name}</span>)
                        : <em>Bota özel eklenti bağlı değil</em>}
                    </div>
                    {canManageBots && dedicatedPlugins.length > 0 ? (
                      <div className="bots-panel__bot-actions">
                        {dedicatedPlugins.map((plugin) => {
                          const linked = bot.plugin_names.includes(plugin.name);
                          const busyKey = `${bot.id}:${plugin.name}`;
                          return (
                            <button
                              type="button"
                              key={plugin.name}
                              className={linked ? "is-linked" : ""}
                              disabled={botPluginBusy === busyKey}
                              onClick={() => handleToggleBotPlugin(bot, plugin)}
                            >
                              {linked ? `${plugin.name} bağlantısını kaldır` : `${plugin.name} bağla`}
                            </button>
                          );
                        })}
                      </div>
                    ) : null}
                    {canManageBots ? (
                      <button
                        type="button"
                        className="bots-panel__remove"
                        disabled={botPluginBusy === `remove:${bot.id}`}
                        onClick={() => void removeBot(bot)}
                      >
                        Sunucudan kaldır
                      </button>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {canManageBots ? (
            <form className="bots-panel__create-card" onSubmit={handleCreateBot}>
              <header><span className="bots-panel__create-icon"><Icon name="bot" /></span><div><span>YENİ BOT</span><h3>Sunucuya bot ekle</h3></div></header>
              <div className="bots-panel__create-fields">
                <label htmlFor="new-bot-name">
                  <span>Bot adı</span>
                  <input
                    id="new-bot-name"
                    value={botName}
                    onChange={(event) => setBotName(event.target.value)}
                    placeholder="Örn. Nexus Müzik"
                    autoComplete="off"
                  />
                </label>
                <label htmlFor="new-bot-plugin">
                  <span>Başlangıç eklentisi</span>
                  <select
                    id="new-bot-plugin"
                    value={selectedPluginName}
                    onChange={(event) => setSelectedPluginName(event.target.value)}
                  >
                    <option value="">Şimdilik bağlama</option>
                    {dedicatedPlugins.map((plugin) => (
                      <option key={plugin.name} value={plugin.name}>{plugin.name}</option>
                    ))}
                  </select>
                </label>
              </div>
              <button className="bots-panel__create-button" type="submit" disabled={creating || !botName.trim()}>
                <Icon name="bot" /> {creating ? "Oluşturuluyor…" : "Botu oluştur"}
              </button>
            </form>
          ) : null}

          <section className="bots-panel__section bots-panel__section--plugins">
            <header className="bots-panel__section-header">
              <div><span>YETENEK KÜTÜPHANESİ</span><h3>Platform eklentileri</h3></div>
              <b>{plugins.length}</b>
            </header>
            <ul className="bots-panel__plugin-list">
              {plugins.map((plugin) => (
                <li key={plugin.name} className={plugin.enabled ? "bots-panel__plugin is-enabled" : "bots-panel__plugin"}>
                  <header className="bots-panel__plugin-header">
                    <div className="bots-panel__plugin-title">
                      <span className="bots-panel__plugin-icon"><Icon name="settings" /></span>
                      <div><strong>{plugin.name}</strong><span>{plugin.enabled ? "Etkin" : "Kurulu değil"}</span></div>
                    </div>
                    <button
                      type="button"
                      className={plugin.enabled ? "bots-panel__plugin-toggle is-remove" : "bots-panel__plugin-toggle"}
                      onClick={() => handleTogglePlugin(plugin)}
                      disabled={!canManageBots || pluginBusy === plugin.name}
                    >
                      {pluginBusy === plugin.name ? "İşleniyor…" : plugin.enabled ? "Kaldır" : "Kur"}
                    </button>
                  </header>
                  <p>{plugin.description || "Bu eklenti için açıklama bulunmuyor."}</p>
                  {plugin.commands.length > 0 ? (
                    <div className="bots-panel__command-list">
                      {plugin.commands.map((command) => <code key={command}>/{command}</code>)}
                    </div>
                  ) : <span className="bots-panel__no-command">Komut gerektirmez</span>}
                  {plugin.requires_bot_link ? (
                    <div className="bots-panel__plugin-note"><Icon name="bot" /> Etkinleştirildikten sonra bir bota bağlanmalıdır.</div>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </>
  );
  if (embedded) return <div className="bots-panel bots-panel--embedded">{body}</div>;
  return <div className="settings-overlay" onClick={onClose}><div className="settings-panel" onClick={(event) => event.stopPropagation()}>{body}</div></div>;
}
