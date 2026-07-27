import { useEffect, useRef, useState } from "react";

import "./App.css";
import { coreApi, getToken, setToken } from "./api/client";
import { ChannelSidebar } from "./components/ChannelSidebar";
import { ChatArea } from "./components/ChatArea";
import { IncomingCallModal, OutgoingCallToast, CallNoticeToast } from "./components/IncomingCallModal";
import { LoginForm } from "./components/LoginForm";
import { MembersPanel } from "./components/MembersPanel";
import { ProfilePanel } from "./components/ProfilePanel";
import { RegisterForm } from "./components/RegisterForm";
import { ServerRail } from "./components/ServerRail";
import { ServerSettingsPanel } from "./components/ServerSettingsPanel";
import { SettingsPanel } from "./components/SettingsPanel";
import { VideoStage } from "./components/VideoStage";
import { useGateway } from "./hooks/useGateway";
import { useVoiceChannel } from "./hooks/useVoiceChannel";
import { playMessageNotification } from "./notifications";
import type { VoiceSettings } from "./settings";
import { loadVoiceSettings } from "./settings";
import type { Channel, ChannelType, Message, Server, User } from "./types";
import { composeAttachmentMessage } from "./messageContent";

const MESSAGE_LIMIT = 50;
const MESSAGE_SYNC_CONNECTED_MS = 30_000;
const MESSAGE_SYNC_DISCONNECTED_MS = 10_000;
const MESSAGE_SYNC_BACKGROUND_MS = 300_000;

function createMessageClientId(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

function mergeIncomingMessage(current: Message[], incoming: Message): Message[] {
  if (current.some((message) => message.event_id === incoming.event_id)) {
    return current.map((message) =>
      message.event_id === incoming.event_id
        ? { ...message, ...incoming, delivery_status: undefined }
        : message,
    );
  }
  const withoutDuplicate = current.filter(
    (message) =>
      message.event_id !== incoming.event_id &&
      (!incoming.client_id || message.client_id !== incoming.client_id),
  );
  return [{ ...incoming }, ...withoutDuplicate];
}

function mergeMessageSnapshot(snapshot: Message[], current: Message[]): Message[] {
  const likelySameMessage = (serverMessage: Message, localMessage: Message) =>
    serverMessage.sender === localMessage.sender &&
    serverMessage.content === localMessage.content &&
    serverMessage.origin_server_ts !== null &&
    localMessage.origin_server_ts !== null &&
    Math.abs(serverMessage.origin_server_ts - localMessage.origin_server_ts) < 120_000;

  const localOnly = current.filter((message) => {
    if (!message.delivery_status) return false;
    if (message.delivery_status === "sending") return true;
    return !snapshot.some((serverMessage) => likelySameMessage(serverMessage, message));
  });
  const localIds = new Set(localOnly.map((message) => message.event_id));
  const refreshed = [
    ...localOnly,
    ...snapshot.filter(
      (message) =>
        !localIds.has(message.event_id) &&
        !localOnly.some((localMessage) => likelySameMessage(message, localMessage)),
    ),
  ];
  const refreshedIds = new Set(refreshed.map((message) => message.event_id));
  // Cursor ile yüklenmiş eski sayfalar, en yeni 50 mesajın periyodik yenilenmesinde bellekte kalır.
  return [...refreshed, ...current.filter((message) => !refreshedIds.has(message.event_id))];
}

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
  const [activeVoiceServerId, setActiveVoiceServerId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [messageCursor, setMessageCursor] = useState<string | null>(null);
  const [hasMoreMessages, setHasMoreMessages] = useState(false);
  const [olderMessagesLoading, setOlderMessagesLoading] = useState(false);
  const [voiceSettings, setVoiceSettings] = useState<VoiceSettings>(() => loadVoiceSettings());
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [serverSettingsOpen, setServerSettingsOpen] = useState(false);
  const [callError, setCallError] = useState<string | null>(null);
  const [voiceStageVisible, setVoiceStageVisible] = useState(true);
  const [membersVisible, setMembersVisible] = useState(false);

  // Sesli kanal ve gateway (presence + çağrı) hook'ları uygulama seviyesinde tutulur ki video
  // ana alanda, kontroller yan panelde gösterilebilsin ve çağrılar her yerde alınabilsin.
  const voice = useVoiceChannel(activeVoiceChannelId, voiceSettings);
  const gateway = useGateway(!!user);

  // Farklı bir sunucudaki kanala (çağrı kabulüyle) katılırken, kanallar yüklendikten sonra
  // hedef ses kanalına geçmek için beklemede tutulan istek.
  const pendingVoiceJoinRef = useRef<{ serverId: number; channelId: number } | null>(null);
  const pendingTextChannelRef = useRef<{ serverId: number; channelId: number } | null>(null);
  const callNotificationRef = useRef<Notification | null>(null);
  const activeChannelIdRef = useRef(activeChannelId);
  activeChannelIdRef.current = activeChannelId;

  // Gelen çağrıda masaüstü bildirimi (sekme arka plandayken bile duyulur). Ayar + izin gerektirir.
  useEffect(() => {
    const call = gateway.incomingCall;
    callNotificationRef.current?.close();
    callNotificationRef.current = null;
    if (!call || !voiceSettings.desktopNotifications || gateway.selfStatus.status === "dnd") return;
    if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
    if (!document.hidden) return; // sekme öndeyse modal zaten görünür
    try {
      const n = new Notification(`${call.fromUsername} seni arıyor`, {
        body: `🔊 ${call.channelName} kanalına davet`,
        tag: "nexus-call",
      });
      n.onclick = () => {
        window.focus();
        n.close();
      };
      callNotificationRef.current = n;
    } catch {
      /* bildirim oluşturulamadı - yok say */
    }
    return () => {
      callNotificationRef.current?.close();
      callNotificationRef.current = null;
    };
  }, [gateway.incomingCall, gateway.selfStatus.status, voiceSettings.desktopNotifications]);

  // Rahatsız etmeyin durumunda çağrı ekranı ve zil hiç açılmaz; arayana doğrudan meşgul yanıtı gider.
  useEffect(() => {
    if (gateway.selfStatus.status === "dnd" && gateway.incomingCall) gateway.rejectCall();
  }, [gateway.incomingCall, gateway.rejectCall, gateway.selfStatus.status]);

  // Tema uygula: koyu = varsayılan (data-theme yok), açık = data-theme="light".
  // "system" seçiliyse işletim sistemi tercihini izler ve anlık değişimi dinler.
  useEffect(() => {
    const root = document.documentElement;
    const apply = (light: boolean) => {
      if (light) root.setAttribute("data-theme", "light");
      else root.removeAttribute("data-theme");
    };
    if (voiceSettings.theme === "system") {
      const mq = window.matchMedia("(prefers-color-scheme: light)");
      apply(mq.matches);
      const handler = (e: MediaQueryListEvent) => apply(e.matches);
      mq.addEventListener("change", handler);
      return () => mq.removeEventListener("change", handler);
    }
    apply(voiceSettings.theme === "light");
  }, [voiceSettings.theme]);

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

  // Metin kanalları arasında gezinmek mevcut ses bağlantısını etkilemez.
  useEffect(() => {
    if (!activeServerId) {
      setChannels([]);
      setActiveChannelId(null);
      return;
    }
    coreApi.listChannels(activeServerId).then((list) => {
      setChannels(list);
      setActiveChannelId((current) =>
        list.some((c) => c.id === current && c.type === "text")
          ? current
          : (list.find((c) => c.type === "text")?.id ?? null),
      );
      // Çağrı kabulü sonrası beklemede bir katılım varsa ve bu sunucuya aitse, hedef kanala gir.
      const pending = pendingVoiceJoinRef.current;
      if (pending && pending.serverId === activeServerId) {
        pendingVoiceJoinRef.current = null;
        if (list.some((c) => c.id === pending.channelId)) {
          setActiveVoiceChannelId(pending.channelId);
          setActiveVoiceServerId(pending.serverId);
        }
      }
      const pendingText = pendingTextChannelRef.current;
      if (pendingText && pendingText.serverId === activeServerId) {
        pendingTextChannelRef.current = null;
        if (list.some((c) => c.id === pendingText.channelId && c.type === "text")) {
          setActiveChannelId(pendingText.channelId);
        }
      }
    });
  }, [activeServerId]);

  // Gateway normal mesajları doğrudan taşır. Bu döngü yalnızca bağlantı kesintileri ve ayrı
  // worker'dan gelen AI cevapları için düşük frekanslı güvenlik ağıdır.
  useEffect(() => {
    if (!activeChannelId) {
      setMessages([]);
      setMessageCursor(null);
      setHasMoreMessages(false);
      return;
    }
    let cancelled = false;
    let timeoutId: number | null = null;
    let loading = false;
    let initialized = false;
    const channelId = activeChannelId;
    setMessages([]);
    setMessageCursor(null);
    setHasMoreMessages(false);

    function nextDelay() {
      if (document.hidden) return MESSAGE_SYNC_BACKGROUND_MS;
      return gateway.connected ? MESSAGE_SYNC_CONNECTED_MS : MESSAGE_SYNC_DISCONNECTED_MS;
    }

    function scheduleNext() {
      if (cancelled) return;
      if (timeoutId !== null) window.clearTimeout(timeoutId);
      timeoutId = window.setTimeout(() => void load(), nextDelay());
    }

    async function load() {
      if (loading || cancelled) return;
      loading = true;
      try {
        const page = await coreApi.listMessages(channelId, MESSAGE_LIMIT);
        if (!cancelled && activeChannelIdRef.current === channelId) {
          setMessages((current) => mergeMessageSnapshot(page.items, current));
          if (!initialized) {
            initialized = true;
            setMessageCursor(page.next_cursor);
            setHasMoreMessages(page.has_more);
          }
        }
      } catch {
        // Gateway çalışmaya devam edebilir; bir sonraki düşük frekanslı senkronizasyonda tekrar denenir.
      } finally {
        loading = false;
        scheduleNext();
      }
    }

    function handleVisibilityChange() {
      if (!document.hidden) {
        if (timeoutId !== null) window.clearTimeout(timeoutId);
        void load();
      } else {
        scheduleNext();
      }
    }

    document.addEventListener("visibilitychange", handleVisibilityChange);
    void load();
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      if (timeoutId !== null) window.clearTimeout(timeoutId);
    };
  }, [activeChannelId, gateway.connected]);

  // Gerçek zamanlı: mesaj payload'ını veya silme olayını doğrudan yerel listeye uygula.
  // Eski backend payload göndermiyorsa geriye uyumluluk için tek seferlik snapshot çekilir.
  useEffect(() => {
    const event = gateway.channelMessage;
    if (!activeChannelId || !event || event.channelId !== activeChannelId) return;
    if (event.deletedEventId) {
      setMessages((current) => current.filter((message) => message.event_id !== event.deletedEventId));
      return;
    }
    if (event.message) {
      setMessages((current) => mergeIncomingMessage(current, event.message!));
      return;
    }
    let cancelled = false;
    coreApi.listMessages(activeChannelId).then((page) => {
      if (!cancelled) setMessages((current) => mergeMessageSnapshot(page.items, current));
    }).catch(() => {});
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gateway.channelMessage?.sequence]);

  useEffect(() => {
    const event = gateway.directMessage;
    if (!event || !user || event.senderId === user.id) return;
    if (gateway.selfStatus.status === "dnd") return;
    const sender = event.message.sender.replace(/^@/, "").split(":")[0];
    if (!document.hidden) return;
    if (voiceSettings.notificationSound) playMessageNotification();
    if (
      document.hidden &&
      voiceSettings.desktopNotifications &&
      typeof Notification !== "undefined" &&
      Notification.permission === "granted"
    ) {
      try {
        const notification = new Notification(`${sender} sana özel mesaj gönderdi`, {
          body: event.message.content.slice(0, 180),
          tag: `nexus-direct-${event.conversationId}`,
        });
        notification.onclick = () => {
          window.focus();
          setProfileOpen(true);
          notification.close();
        };
      } catch {
        /* uygulama içi bildirim devam eder */
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gateway.directMessage?.sequence]);

  // Aktif olmayan kanallardaki mesajlar için kenar bildirimi, kısa ses ve izin verilmişse
  // tarayıcı dışı sistem bildirimi üret. DND bütün yolları tek noktadan kapatır.
  useEffect(() => {
    const event = gateway.channelMessage;
    const message = event?.message;
    if (!event || !message || !user || message.sender === user.matrix_user_id) return;
    if (gateway.selfStatus.status === "dnd") return;
    if (!document.hidden) return;

    const sender = message.sender.replace(/^@/, "").split(":")[0];
    if (voiceSettings.notificationSound) playMessageNotification();
    if (
      voiceSettings.desktopNotifications &&
      typeof Notification !== "undefined" &&
      Notification.permission === "granted"
    ) {
      try {
        const notification = new Notification(`${sender} yeni bir mesaj gönderdi`, {
          body: message.content.slice(0, 180),
          tag: `nexus-message-${event.channelId}`,
        });
        notification.onclick = () => {
          window.focus();
          if (event.serverId === activeServerId) setActiveChannelId(event.channelId);
          else {
            pendingTextChannelRef.current = {
              serverId: event.serverId,
              channelId: event.channelId,
            };
            setActiveServerId(event.serverId);
          }
          notification.close();
        };
      } catch {
        /* sistem bildirimi kullanılamıyorsa sessizce devam et */
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gateway.channelMessage?.sequence]);

  async function handleLoadOlderMessages() {
    if (!activeChannelId || !messageCursor || olderMessagesLoading) return;
    const channelId = activeChannelId;
    setOlderMessagesLoading(true);
    try {
      const page = await coreApi.listMessages(channelId, MESSAGE_LIMIT, messageCursor);
      if (activeChannelIdRef.current !== channelId) return;
      setMessages((current) => {
        const known = new Set(current.map((message) => message.event_id));
        return [...current, ...page.items.filter((message) => !known.has(message.event_id))];
      });
      setMessageCursor(page.next_cursor);
      setHasMoreMessages(page.has_more);
    } catch (err) {
      setCallError(err instanceof Error ? err.message : "Eski mesajlar yüklenemedi");
    } finally {
      setOlderMessagesLoading(false);
    }
  }

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
      const { access_token } = await coreApi.login(username, password);
      setToken(access_token);
      setUser(await coreApi.me());
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "Kayıt başarısız");
    }
  }

  function handleLogout() {
    setProfileOpen(false);
    setSettingsOpen(false);
    setServerSettingsOpen(false);
    setToken(null);
    setUser(null);
    setServers([]);
    setActiveServerId(null);
    setChannels([]);
    setActiveChannelId(null);
    setActiveVoiceChannelId(null);
    setActiveVoiceServerId(null);
    setMessages([]);
  }

  async function handleCreateServer(name: string) {
    const server = await coreApi.createServer(name);
    setServers((prev) => [...prev, server]);
    setActiveServerId(server.id);
  }

  async function handleUpdateServer(
    serverId: number,
    patch: { name: string; description: string | null },
  ) {
    try {
      const updated = await coreApi.updateServer(serverId, patch);
      setServers((prev) => prev.map((s) => (s.id === serverId ? updated : s)));
    } catch (err) {
      setCallError(err instanceof Error ? err.message : "Sunucu yeniden adlandırılamadı");
    }
  }

  function dropServer(serverId: number) {
    if (activeVoiceServerId === serverId) {
      setActiveVoiceChannelId(null);
      setActiveVoiceServerId(null);
    }
    setServers((prev) => {
      const remaining = prev.filter((s) => s.id !== serverId);
      setActiveServerId((current) => (current === serverId ? (remaining[0]?.id ?? null) : current));
      return remaining;
    });
  }

  async function handleDeleteServer(serverId: number) {
    const server = servers.find((s) => s.id === serverId);
    if (!window.confirm(`"${server?.name ?? "sunucu"}" sunucusu kalıcı olarak silinsin mi? Bu geri alınamaz.`))
      return;
    try {
      await coreApi.deleteServer(serverId);
      dropServer(serverId);
    } catch (err) {
      setCallError(err instanceof Error ? err.message : "Sunucu silinemedi");
    }
  }

  async function handleLeaveServer(serverId: number) {
    const server = servers.find((s) => s.id === serverId);
    if (!window.confirm(`"${server?.name ?? "sunucu"}" sunucusundan ayrılmak istiyor musun?`)) return;
    try {
      await coreApi.removeMember(serverId, user!.id);
      dropServer(serverId);
    } catch (err) {
      setCallError(err instanceof Error ? err.message : "Sunucudan ayrılınamadı");
    }
  }

  async function handleCreateChannel(name: string, type: ChannelType) {
    if (!activeServerId) return;
    const channel = await coreApi.createChannel(activeServerId, name, type);
    setChannels((prev) => [...prev, channel]);
    if (type === "voice") {
      setActiveVoiceChannelId(channel.id);
      setActiveVoiceServerId(activeServerId);
    } else {
      setActiveChannelId(channel.id);
    }
  }

  function handleToggleVoice(channelId: number) {
    setVoiceStageVisible(true);
    if (activeVoiceChannelId === channelId) {
      setActiveVoiceChannelId(null);
      setActiveVoiceServerId(null);
    } else {
      setActiveVoiceChannelId(channelId);
      setActiveVoiceServerId(activeServerId);
    }
  }

  async function handleRenameChannel(channelId: number) {
    if (!activeServerId) return;
    const channel = channels.find((c) => c.id === channelId);
    const name = window.prompt("Yeni kanal adı:", channel?.name ?? "");
    if (name == null) return;
    const trimmed = name.trim();
    if (!trimmed) return;
    try {
      const updated = await coreApi.updateChannel(activeServerId, channelId, { name: trimmed });
      setChannels((prev) => prev.map((c) => (c.id === channelId ? updated : c)));
    } catch (err) {
      setCallError(err instanceof Error ? err.message : "Kanal yeniden adlandırılamadı");
    }
  }

  async function handleDeleteChannel(channelId: number) {
    if (!activeServerId) return;
    const channel = channels.find((c) => c.id === channelId);
    if (!window.confirm(`"${channel?.name ?? "kanal"}" kanalı silinsin mi? Bu geri alınamaz.`)) return;
    try {
      await coreApi.deleteChannel(activeServerId, channelId);
      setChannels((prev) => prev.filter((c) => c.id !== channelId));
      setActiveChannelId((current) => (current === channelId ? null : current));
      setActiveVoiceChannelId((current) => (current === channelId ? null : current));
      if (activeVoiceChannelId === channelId && activeVoiceServerId === activeServerId) {
        setActiveVoiceServerId(null);
      }
    } catch (err) {
      setCallError(err instanceof Error ? err.message : "Kanal silinemedi");
    }
  }

  function joinVoiceChannel(serverId: number, channelId: number) {
    if (serverId === activeServerId) {
      setActiveVoiceChannelId(channelId);
      setActiveVoiceServerId(serverId);
    } else {
      pendingVoiceJoinRef.current = { serverId, channelId };
      setActiveServerId(serverId);
    }
  }

  // Bir üyeyi ses kanalına çağır: arayan da kanala girer, hedefe zil gider.
  function handleCallMember(userId: number, username: string) {
    setCallError(null);
    const targetChannel = activeVoiceChannelId
      ? channels.find((c) => c.id === activeVoiceChannelId)
      : channels.find((c) => c.type === "voice");
    if (!targetChannel) {
      setCallError("Bu sunucuda ses kanalı yok. Önce bir ses kanalı oluşturun.");
      return;
    }
    setActiveVoiceChannelId(targetChannel.id);
    setActiveVoiceServerId(targetChannel.server_id);
    setVoiceStageVisible(true);
    gateway.inviteToCall(targetChannel.id, userId, username);
  }

  function handleAcceptCall() {
    const call = gateway.acceptCall();
    if (call) joinVoiceChannel(call.serverId, call.channelId);
  }

  async function handleSendMessage(content: string, file?: File) {
    if (!activeChannelId) return;
    const channelId = activeChannelId;
    let outgoingContent = content;
    if (file) {
      try {
        const attachment = await coreApi.uploadAttachment(file);
        outgoingContent = composeAttachmentMessage(attachment, content);
      } catch (err) {
        setCallError(err instanceof Error ? err.message : "Dosya yüklenemedi");
        return;
      }
    }
    const clientId = createMessageClientId();
    const optimistic: Message = {
      event_id: `pending-${clientId}`,
      sender: user?.matrix_user_id ?? `@${user?.username ?? "sen"}:nexus`,
      content: outgoingContent,
      origin_server_ts: Date.now(),
      client_id: clientId,
      delivery_status: "sending",
    };
    setMessages((current) => mergeIncomingMessage(current, optimistic));
    try {
      const sent = await coreApi.sendMessage(channelId, outgoingContent, clientId);
      if (activeChannelIdRef.current === channelId) {
        setMessages((current) =>
          sent.hidden
            ? current.filter((message) => message.client_id !== clientId)
            : mergeIncomingMessage(current, sent),
        );
      }
    } catch (err) {
      if (activeChannelIdRef.current === channelId) {
        setMessages((current) =>
          current.map((message) =>
            message.client_id === clientId ? { ...message, delivery_status: "failed" } : message,
          ),
        );
      }
      setCallError(err instanceof Error ? err.message : "Mesaj gönderilemedi");
    }
  }

  async function handleEditMessage(eventId: string, content: string) {
    if (!activeChannelId) return;
    const channelId = activeChannelId;
    const previous = messages.find((message) => message.event_id === eventId);
    setMessages((current) =>
      current.map((message) =>
        message.event_id === eventId ? { ...message, content, edited: true } : message,
      ),
    );
    try {
      await coreApi.editMessage(channelId, eventId, content);
    } catch (err) {
      if (previous) {
        setMessages((current) =>
          current.map((message) => (message.event_id === eventId ? previous : message)),
        );
      }
      setCallError(err instanceof Error ? err.message : "Mesaj düzenlenemedi");
    }
  }

  function handleRetryMessage(clientId: string, content: string) {
    setMessages((current) => current.filter((message) => message.client_id !== clientId));
    void handleSendMessage(content);
  }

  async function handleDeleteMessage(eventId: string) {
    if (!activeChannelId) return;
    const channelId = activeChannelId;
    // İyimser güncelleme: mesajı hemen kaldır, sonra sunucu sonucuyla senkronize et.
    setMessages((prev) => prev.filter((m) => m.event_id !== eventId));
    const removed = messages.find((message) => message.event_id === eventId);
    try {
      await coreApi.deleteMessage(channelId, eventId);
    } catch (err) {
      if (removed && activeChannelIdRef.current === channelId) {
        setMessages((current) => mergeIncomingMessage(current, removed));
      }
      setCallError(err instanceof Error ? err.message : "Mesaj silinemedi");
    }
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
    <div className={membersVisible ? "app-shell app-shell--members-open" : "app-shell"}>
      <ServerRail
        servers={servers}
        activeServerId={activeServerId}
        onSelect={setActiveServerId}
        onCreateServer={handleCreateServer}
      />
      {activeServer && membersVisible ? (
        <MembersPanel
          serverId={activeServer.id}
          serverName={activeServer.name}
          canInvite={activeServer.owner_id === user.id}
          currentUserId={user.id}
          presences={gateway.presences}
          onCallMember={handleCallMember}
          onClose={() => setMembersVisible(false)}
        />
      ) : null}
      <ChannelSidebar
        server={activeServer}
        channels={channels}
        activeChannelId={activeChannelId}
        onSelect={setActiveChannelId}
        activeVoiceChannelId={activeVoiceServerId === activeServerId ? activeVoiceChannelId : null}
        onToggleVoice={handleToggleVoice}
        currentUser={user}
        voiceSettings={voiceSettings}
        voice={voice}
        canCreateChannel={activeServer?.owner_id === user.id}
        onCreateChannel={handleCreateChannel}
        onRenameChannel={handleRenameChannel}
        onDeleteChannel={handleDeleteChannel}
        onOpenServerSettings={() => setServerSettingsOpen(true)}
        voiceStates={gateway.voiceStates}
        onOpenProfile={() => setProfileOpen(true)}
        onOpenSettings={() => setSettingsOpen(true)}
      />
      <div className={voiceStageVisible && voice.connected ? "app-main" : "app-main app-main--chat-focus"}>
        <header className="app-main__toolbar">
          <div className="app-main__context">
            <span>{activeServer?.name ?? "Nexus"}</span>
            <strong>
              {activeChannel
                ? `${activeChannel.type === "voice" ? "Ses" : "#"} ${activeChannel.name}`
                : "Genel görünüm"}
            </strong>
          </div>
          <div className="app-main__toolbar-actions">
            {voice.connected ? (
              <span className="connection-pill">
                <span className="connection-pill__dot" />
                Ses bağlı
              </span>
            ) : null}
            {activeServer ? (
              <button
                type="button"
                className={membersVisible ? "toolbar-action toolbar-action--active" : "toolbar-action"}
                onClick={() => setMembersVisible((visible) => !visible)}
              >
                {membersVisible ? "Üyeleri kapat" : "Üyeler"}
              </button>
            ) : null}
            {voice.connected ? (
              <button
                type="button"
                className="toolbar-action"
                onClick={() => setVoiceStageVisible((visible) => !visible)}
              >
                {voiceStageVisible ? "Sahneyi gizle" : "Canlı sahneyi göster"}
              </button>
            ) : null}
          </div>
        </header>
        {voiceStageVisible && voice.connected ? <VideoStage
          currentUser={user}
          participants={voice.participants}
          voice={voice}
          qualityLabel={`${voiceSettings.videoQuality} · ${voiceSettings.videoFrameRate} FPS`}
          onHide={() => setVoiceStageVisible(false)}
          onLeave={() => {
            if (activeVoiceChannelId) handleToggleVoice(activeVoiceChannelId);
          }}
        /> : null}
        <ChatArea
          channel={activeChannel}
          messages={messages}
          currentMatrixUserId={user.matrix_user_id}
          onSendMessage={handleSendMessage}
          onEditMessage={handleEditMessage}
          onDeleteMessage={handleDeleteMessage}
          onRetryMessage={handleRetryMessage}
          hasMoreMessages={hasMoreMessages}
          loadingOlder={olderMessagesLoading}
          onLoadOlder={handleLoadOlderMessages}
        />
      </div>
      {profileOpen ? (
        <ProfilePanel
          currentUser={user}
          presences={gateway.presences}
          directMessage={gateway.directMessage}
          socialEventSequence={gateway.socialEventSequence}
          onClose={() => setProfileOpen(false)}
          onOpenSettings={() => setSettingsOpen(true)}
          onLogout={handleLogout}
        />
      ) : null}
      {activeServer && serverSettingsOpen ? (
        <ServerSettingsPanel
          server={activeServer}
          canManage={activeServer.owner_id === user.id}
          onClose={() => setServerSettingsOpen(false)}
          onSave={(patch) => handleUpdateServer(activeServer.id, patch)}
          onDelete={() => {
            setServerSettingsOpen(false);
            void handleDeleteServer(activeServer.id);
          }}
          onLeave={() => {
            setServerSettingsOpen(false);
            void handleLeaveServer(activeServer.id);
          }}
        />
      ) : null}
      {settingsOpen ? (
        <SettingsPanel
          settings={voiceSettings}
          currentUser={user}
          onUserUpdated={setUser}
          onClose={() => setSettingsOpen(false)}
          onChange={setVoiceSettings}
          selfStatus={gateway.selfStatus}
          onStatusChange={gateway.setStatus}
        />
      ) : null}

      {gateway.incomingCall && gateway.selfStatus.status !== "dnd" ? (
        <IncomingCallModal
          call={gateway.incomingCall}
          sound={voiceSettings.callRingtone}
          onAccept={handleAcceptCall}
          onReject={gateway.rejectCall}
        />
      ) : null}
      {gateway.outgoingCall ? (
        <OutgoingCallToast call={gateway.outgoingCall} onCancel={gateway.cancelCall} />
      ) : null}
      {gateway.notice ? (
        <CallNoticeToast notice={gateway.notice} onDismiss={gateway.clearNotice} />
      ) : null}
      {callError ? (
        <CallNoticeToast notice={{ kind: "error", text: callError }} onDismiss={() => setCallError(null)} />
      ) : null}
    </div>
  );
}
