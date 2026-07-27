import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { ApiError, coreApi } from "../api/client";
import type { Bot, PluginManifest } from "../types";

interface BotsPanelProps {
  serverId: number;
  serverName: string;
  canManageBots: boolean;
  onClose: () => void;
}

export function BotsPanel({ serverId, serverName, canManageBots, onClose }: BotsPanelProps) {
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

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-panel" onClick={(event) => event.stopPropagation()}>
        <header className="settings-panel__header">
          <h2>{serverName} — Botlar</h2>
          <button className="settings-panel__close" onClick={onClose} aria-label="Kapat">
            ✕
          </button>
        </header>

        {loading ? (
          <div>Yükleniyor...</div>
        ) : (
          <>
            <div className="settings-panel__section">
              <strong>Bu sunucudaki botlar</strong>
              {bots.length === 0 ? (
                <div className="members-panel__empty">Henüz bot eklenmemiş.</div>
              ) : (
                <ul className="members-panel__list">
                  {bots.map((bot) => (
                    <li key={bot.id} className="bots-panel__bot-card">
                      <div>
                        <strong>{bot.name}</strong>{" "}
                        <span className="bots-panel__prefix">({bot.command_prefix})</span>
                        <div className="bots-panel__plugin-commands">
                          {bot.plugin_names.length > 0
                            ? `Bağlı: ${bot.plugin_names.join(", ")}`
                            : "Bota özel plugin bağlı değil"}
                        </div>
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
                                disabled={botPluginBusy === busyKey}
                                onClick={() => handleToggleBotPlugin(bot, plugin)}
                              >
                                {linked ? `${plugin.name} kaldır` : `${plugin.name} bağla`}
                              </button>
                            );
                          })}
                        </div>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {canManageBots ? (
              <form className="settings-panel__section" onSubmit={handleCreateBot}>
                <label htmlFor="new-bot-name">Yeni bot oluştur ve sunucuya ekle</label>
                <input
                  id="new-bot-name"
                  value={botName}
                  onChange={(event) => setBotName(event.target.value)}
                  placeholder="bot-adi"
                />
                {dedicatedPlugins.length > 0 ? (
                  <>
                    <label htmlFor="new-bot-plugin">Bota özel plugin (isteğe bağlı)</label>
                    <select
                      id="new-bot-plugin"
                      value={selectedPluginName}
                      onChange={(event) => setSelectedPluginName(event.target.value)}
                    >
                      <option value="">Plugin bağlama</option>
                      {dedicatedPlugins.map((plugin) => (
                        <option key={plugin.name} value={plugin.name}>
                          {plugin.name}
                        </option>
                      ))}
                    </select>
                  </>
                ) : null}
                <button type="submit" disabled={creating || !botName.trim()}>
                  {creating ? "Oluşturuluyor..." : "Oluştur"}
                </button>
              </form>
            ) : null}

            {error ? <div className="members-panel__error">{error}</div> : null}
            {notice ? <div className="members-panel__notice">{notice}</div> : null}

            <div className="settings-panel__section">
              <strong>Platform pluginleri</strong>
              <ul className="bots-panel__plugin-list">
                {plugins.map((plugin) => (
                  <li key={plugin.name} className="bots-panel__plugin">
                    <div>
                      <div>{plugin.name}</div>
                      {plugin.commands.length > 0 ? (
                        <div className="bots-panel__command-list">
                          {plugin.commands.map((command) => (
                            <code key={command}>{command}</code>
                          ))}
                        </div>
                      ) : null}
                      {plugin.requires_bot_link ? (
                        <div className="bots-panel__plugin-note">
                          Kurulduktan sonra yukarıdaki bir bota bağlanmalıdır.
                        </div>
                      ) : null}
                    </div>
                    <button onClick={() => handleTogglePlugin(plugin)} disabled={pluginBusy === plugin.name}>
                      {plugin.enabled ? "Kaldır" : "Kur"}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
