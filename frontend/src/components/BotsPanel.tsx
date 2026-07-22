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
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pluginBusy, setPluginBusy] = useState<string | null>(null);

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
      setNotice(`${trimmed} botu oluşturuldu ve sunucuya eklendi.`);
      setBotName("");
      loadAll();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Bot oluşturulamadı");
    } finally {
      setCreating(false);
    }
  }

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
                    <li key={bot.id}>
                      {bot.name} <span className="bots-panel__prefix">({bot.command_prefix})</span>
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
                        <div className="bots-panel__plugin-commands">{plugin.commands.join(", ")}</div>
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
