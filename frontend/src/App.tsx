import { useEffect, useState } from "react";

import "./App.css";
import { coreApi, getToken, setToken } from "./api/client";
import { ChannelSidebar } from "./components/ChannelSidebar";
import { ChatArea } from "./components/ChatArea";
import { LoginForm } from "./components/LoginForm";
import { RegisterForm } from "./components/RegisterForm";
import { ServerRail } from "./components/ServerRail";
import { SettingsPanel } from "./components/SettingsPanel";
import type { VoiceSettings } from "./settings";
import { loadVoiceSettings } from "./settings";
import type { Channel, ChannelType, Message, Server, User } from "./types";

const MESSAGE_POLL_MS = 4000;

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");

  const [servers, setServers] = useState<Server[]>([]);
  const [activeServerId, setActiveServerId] = useState<number | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [activeChannelId, setActiveChannelId] = useState<number | null>(null);
  const [activeVoiceChannelId, setActiveVoiceChannelId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [voiceSettings, setVoiceSettings] = useState<VoiceSettings>(() => loadVoiceSettings());
  const [settingsOpen, setSettingsOpen] = useState(false);

  // İlk açılışta saklı bir token varsa oturumu doğrula.
  useEffect(() => {
    if (!getToken()) {
      setAuthChecked(true);
      return;
    }
    coreApi
      .me()
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setAuthChecked(true));
  }, []);

  // Kullanıcı girişi tamamlanınca üyesi olduğu sunucuları çek.
  useEffect(() => {
    if (!user) return;
    coreApi.myServers().then((list) => {
      setServers(list);
      setActiveServerId((current) => current ?? list[0]?.id ?? null);
    });
  }, [user]);

  // Aktif sunucu değişince kanallarını çek. Sesli kanaldan da ayrıl - VoicePanel
  // unmount olacağı için bağlantı zaten kapanır, activeVoiceChannelId'yi de sıfırlamazsak
  // aynı id'li bir kanala tekrar dönüldüğünde "bağlıymış gibi" görünüp bağlı olmaz.
  useEffect(() => {
    setActiveVoiceChannelId(null);
    if (!activeServerId) {
      setChannels([]);
      setActiveChannelId(null);
      return;
    }
    coreApi.listChannels(activeServerId).then((list) => {
      setChannels(list);
      setActiveChannelId((current) => (list.some((c) => c.id === current) ? current : (list[0]?.id ?? null)));
    });
  }, [activeServerId]);

  // Aktif kanal değişince mesajlarını çek, birkaç saniyede bir yenile.
  useEffect(() => {
    if (!activeChannelId) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    const channelId = activeChannelId;

    function load() {
      coreApi.listMessages(channelId).then((list) => {
        if (!cancelled) setMessages(list);
      });
    }

    load();
    const interval = setInterval(load, MESSAGE_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [activeChannelId]);

  async function handleLogin(username: string, password: string) {
    setAuthError(null);
    try {
      const { access_token } = await coreApi.login(username, password);
      setToken(access_token);
      setUser(await coreApi.me());
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "Giriş başarısız");
    }
  }

  async function handleRegister(username: string, email: string, password: string) {
    setAuthError(null);
    try {
      await coreApi.register(username, email, password);
      // Kayıt sonrası otomatik giriş yap.
      const { access_token } = await coreApi.login(username, password);
      setToken(access_token);
      setUser(await coreApi.me());
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "Kayıt başarısız");
    }
  }

  function handleLogout() {
    setToken(null);
    setUser(null);
    setServers([]);
    setActiveServerId(null);
    setChannels([]);
    setActiveChannelId(null);
    setMessages([]);
  }

  async function handleCreateServer(name: string) {
    const server = await coreApi.createServer(name);
    setServers((prev) => [...prev, server]);
    setActiveServerId(server.id);
  }

  async function handleCreateChannel(name: string, type: ChannelType) {
    if (!activeServerId) return;
    const channel = await coreApi.createChannel(activeServerId, name, type);
    setChannels((prev) => [...prev, channel]);
    if (type === "voice") {
      setActiveVoiceChannelId(channel.id);
    } else {
      setActiveChannelId(channel.id);
    }
  }

  function handleToggleVoice(channelId: number) {
    setActiveVoiceChannelId((current) => (current === channelId ? null : channelId));
  }

  async function handleSendMessage(content: string) {
    if (!activeChannelId) return;
    await coreApi.sendMessage(activeChannelId, content);
    setMessages(await coreApi.listMessages(activeChannelId));
  }

  if (!authChecked) {
    return <div className="app-loading">Yükleniyor...</div>;
  }

  if (!user) {
    return authMode === "login" ? (
      <LoginForm onLogin={handleLogin} onSwitchToRegister={() => { setAuthError(null); setAuthMode("register"); }} error={authError} />
    ) : (
      <RegisterForm
        onRegister={handleRegister}
        onSwitchToLogin={() => { setAuthError(null); setAuthMode("login"); }}
        error={authError}
      />
    );
  }

  const activeServer = servers.find((s) => s.id === activeServerId);
  const activeChannel = channels.find((c) => c.id === activeChannelId);

  return (
    <div className="app-shell">
      <ServerRail
        servers={servers}
        activeServerId={activeServerId}
        onSelect={setActiveServerId}
        onCreateServer={handleCreateServer}
      />
      <ChannelSidebar
        server={activeServer}
        channels={channels}
        activeChannelId={activeChannelId}
        onSelect={setActiveChannelId}
        activeVoiceChannelId={activeVoiceChannelId}
        onToggleVoice={handleToggleVoice}
        currentUser={user}
        voiceSettings={voiceSettings}
        canCreateChannel={activeServer?.owner_id === user.id}
        onCreateChannel={handleCreateChannel}
      />
      <ChatArea
        channel={activeChannel}
        messages={messages}
        currentMatrixUserId={user.matrix_user_id}
        onSendMessage={handleSendMessage}
      />
      <div className="app-shell__top-actions">
        <button className="settings-button" onClick={() => setSettingsOpen(true)} title="Ses ayarları">
          ⚙️
        </button>
        <button className="logout-button" onClick={handleLogout} title={`${user.username} olarak çıkış yap`}>
          Çıkış ({user.username})
        </button>
      </div>
      {settingsOpen ? (
        <SettingsPanel
          settings={voiceSettings}
          onClose={() => setSettingsOpen(false)}
          onChange={setVoiceSettings}
        />
      ) : null}
    </div>
  );
}
