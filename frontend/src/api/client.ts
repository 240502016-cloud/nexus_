// Core API'ye konuşan ince bir fetch sarmalayıcısı.
// Geliştirmede /api -> vite.config.ts proxy'si üzerinden http://localhost:8000'e yönlenir.

import type {
  AiConversation,
  AiJob,
  Bot,
  Attachment,
  Channel,
  ChannelType,
  DirectConversation,
  Friend,
  FriendRequest,
  FriendRequestList,
  LoginResponse,
  Member,
  Message,
  MessagePage,
  MessageReactionUpdate,
  PinnedMessages,
  PluginManifest,
  PublicUser,
  Server,
  ServerInvite,
  ServerInviteList,
  ServerJoinCode,
  User,
} from "../types";
import { apiUrl, desktopBridge } from "../desktopBridge";

const TOKEN_STORAGE_KEY = "nexus_token";

let token: string | null = desktopBridge.available ? null : localStorage.getItem(TOKEN_STORAGE_KEY);

export async function initializeTokenStorage(): Promise<void> {
  if (!desktopBridge.available) return;
  token = await desktopBridge.getSecureToken();
  // Eski geliştirme sürümünden kalmış düz metin tokenı masaüstünde tutma.
  localStorage.removeItem(TOKEN_STORAGE_KEY);
}

export function getToken(): string | null {
  return token;
}

export function setToken(newToken: string | null): void {
  token = newToken;
  if (desktopBridge.available) {
    void desktopBridge.setSecureToken(newToken);
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    return;
  }
  if (newToken) {
    localStorage.setItem(TOKEN_STORAGE_KEY, newToken);
  } else {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

interface RequestOptions extends RequestInit {
  retry?: boolean;
  maxAttempts?: number;
  retryBaseMs?: number;
  timeoutMs?: number;
}

const RETRYABLE_STATUSES = new Set([502, 503, 504]);

function retryDelay(attempt: number, baseMs = 350): Promise<void> {
  const delay = Math.min(1_500, baseMs * 2 ** attempt) + Math.round(Math.random() * 100);
  return new Promise((resolve) => window.setTimeout(resolve, delay));
}

async function request<T>(path: string, init?: RequestOptions): Promise<T> {
  const {
    retry,
    maxAttempts: requestedMaxAttempts,
    retryBaseMs = 350,
    timeoutMs = 15_000,
    ...fetchInit
  } = init ?? {};
  const headers: Record<string, string> = { ...(init?.headers as Record<string, string> | undefined) };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  // FormData ve URLSearchParams'ta Content-Type'ı tarayıcı belirler (multipart boundary vb.).
  if (init?.body && !(init.body instanceof URLSearchParams) && !(init.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  const method = (fetchInit.method ?? "GET").toUpperCase();
  const canRetry = retry ?? (method === "GET" || method === "HEAD");
  const maxAttempts = canRetry ? Math.max(1, requestedMaxAttempts ?? 3) : 1;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    let response: Response;
    try {
      response = await fetch(apiUrl(path), { ...fetchInit, headers, signal: controller.signal });
    } catch (error) {
      window.clearTimeout(timer);
      if (attempt + 1 < maxAttempts) {
        await retryDelay(attempt, retryBaseMs);
        continue;
      }
      const timeout = error instanceof DOMException && error.name === "AbortError";
      throw new ApiError(
        0,
        timeout
          ? "Sunucu yanıt vermedi. Bağlantı yeniden kurulunca tekrar deneyin."
          : "Sunucuya ulaşılamadı. İnternet veya sunucu bağlantınızı kontrol edin.",
      );
    }
    window.clearTimeout(timer);

    if (!response.ok) {
      if (RETRYABLE_STATUSES.has(response.status) && attempt + 1 < maxAttempts) {
        await retryDelay(attempt, retryBaseMs);
        continue;
      }
      let detail = response.statusText;
      try {
        const body = await response.json();
        detail = body.detail ?? detail;
      } catch {
        // yanıt gövdesi JSON değilse statusText'e düş
      }
      throw new ApiError(response.status, detail);
    }

    if (response.status === 204) {
      return undefined as T;
    }
    return response.json() as Promise<T>;
  }
  throw new ApiError(0, "İstek tamamlanamadı.");
}

export const coreApi = {
  health: () => request<{ status: string }>("/health"),

  voiceIceServers: () =>
    request<{ ice_servers: RTCIceServer[]; expires_at: number }>("/voice/ice-servers", {
      retry: false,
      timeoutMs: 1_500,
    }),

  login: (username: string, password: string) => {
    const body = new URLSearchParams({ username, password });
    return request<LoginResponse>("/auth/login", {
      method: "POST",
      body,
      retry: true,
      maxAttempts: 8,
      retryBaseMs: 200,
      timeoutMs: 8_000,
    });
  },

  register: (username: string, email: string, password: string) =>
    request<User>("/users", {
      method: "POST",
      body: JSON.stringify({ username, email, password }),
      retry: true,
      maxAttempts: 8,
      retryBaseMs: 200,
      timeoutMs: 20_000,
    }),

  me: () => request<User>("/users/me"),
  updateProfile: (displayName: string | null) =>
    request<User>("/users/me", { method: "PATCH", body: JSON.stringify({ display_name: displayName }) }),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<void>("/users/me/password", {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }),
  uploadAvatar: (blob: Blob) => {
    const form = new FormData();
    form.append("file", blob, "avatar");
    return request<User>("/users/me/avatar", { method: "POST", body: form });
  },
  searchUsers: (query: string) =>
    request<PublicUser[]>(`/users/search?q=${encodeURIComponent(query)}`),

  listFriends: () => request<Friend[]>("/friends"),
  listFriendRequests: () => request<FriendRequestList>("/friends/requests"),
  sendFriendRequest: (username: string) =>
    request<FriendRequest>("/friends/requests", {
      method: "POST",
      body: JSON.stringify({ username }),
      retry: true,
    }),
  acceptFriendRequest: (friendshipId: number) =>
    request<Friend>(`/friends/requests/${friendshipId}/accept`, { method: "POST", retry: true }),
  removeFriendship: (friendshipId: number) =>
    request<void>(`/friends/${friendshipId}`, { method: "DELETE", retry: true }),

  listDirectConversations: () => request<DirectConversation[]>("/direct/conversations"),
  listDirectMessages: (conversationId: number, limit = 50, cursor?: string | null) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cursor) params.set("cursor", cursor);
    return request<MessagePage>(
      `/direct/conversations/${conversationId}/messages?${params.toString()}`,
    );
  },
  sendDirectMessage: (
    conversationId: number,
    content: string,
    clientId: string,
    replyToEventId?: string,
  ) =>
    request<Message>(`/direct/conversations/${conversationId}/messages`, {
      method: "POST",
      body: JSON.stringify({
        content,
        client_id: clientId,
        reply_to_event_id: replyToEventId,
      }),
    }),
  editDirectMessage: (conversationId: number, eventId: string, content: string) =>
    request<Message>(
      `/direct/conversations/${conversationId}/messages/${encodeURIComponent(eventId)}`,
      { method: "PATCH", body: JSON.stringify({ content }) },
    ),

  myServers: () => request<Server[]>("/servers"),
  createServer: (name: string) =>
    request<Server>("/servers", { method: "POST", body: JSON.stringify({ name }) }),
  updateServer: (serverId: number, patch: { name?: string; description?: string | null }) =>
    request<Server>(`/servers/${serverId}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteServer: (serverId: number) => request<void>(`/servers/${serverId}`, { method: "DELETE" }),

  listMembers: (serverId: number) => request<Member[]>(`/servers/${serverId}/members`),
  addMember: (serverId: number, userId: number) =>
    request<ServerInvite>(`/servers/${serverId}/members`, {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
      retry: true,
    }),
  listServerInvites: () => request<ServerInviteList>("/server-invites"),
  acceptServerInvite: (inviteId: number) =>
    request<Server>(`/server-invites/${inviteId}/accept`, { method: "POST", retry: true }),
  declineServerInvite: (inviteId: number) =>
    request<void>(`/server-invites/${inviteId}`, { method: "DELETE", retry: true }),
  getServerJoinCode: (serverId: number) =>
    request<ServerJoinCode>(`/server-join/servers/${serverId}/code`),
  createServerJoinCode: (serverId: number) =>
    request<ServerJoinCode>(`/server-join/servers/${serverId}/code`, {
      method: "POST",
      retry: true,
    }),
  rotateServerJoinCode: (serverId: number) =>
    request<ServerJoinCode>(`/server-join/servers/${serverId}/code`, {
      method: "PUT",
    }),
  revokeServerJoinCode: (serverId: number) =>
    request<void>(`/server-join/servers/${serverId}/code`, { method: "DELETE", retry: true }),
  joinServerByCode: (code: string) =>
    request<Server>("/server-join", {
      method: "POST",
      body: JSON.stringify({ code }),
      retry: true,
    }),
  removeMember: (serverId: number, userId: number) =>
    request<void>(`/servers/${serverId}/members/${userId}`, { method: "DELETE" }),

  listPlugins: () => request<PluginManifest[]>("/plugins"),
  installPlugin: (name: string) =>
    request<PluginManifest>(`/plugins/${encodeURIComponent(name)}/install`, { method: "POST" }),
  uninstallPlugin: (name: string) =>
    request<{ status: string }>(`/plugins/${encodeURIComponent(name)}/uninstall`, { method: "POST" }),

  listServerBots: (serverId: number) => request<Bot[]>(`/servers/${serverId}/bots`),
  createBot: (name: string, commandPrefix = "/") =>
    request<Bot>("/bots", { method: "POST", body: JSON.stringify({ name, command_prefix: commandPrefix }) }),
  addBotToServer: (botId: number, serverId: number) =>
    request<{ status: string }>(`/bots/${botId}/servers/${serverId}`, { method: "POST" }),
  linkPluginToBot: (serverId: number, botId: number, pluginName: string) =>
    request<{ status: string }>(
      `/servers/${serverId}/bots/${botId}/plugins/${encodeURIComponent(pluginName)}`,
      { method: "POST" },
    ),
  unlinkPluginFromBot: (serverId: number, botId: number, pluginName: string) =>
    request<void>(
      `/servers/${serverId}/bots/${botId}/plugins/${encodeURIComponent(pluginName)}`,
      { method: "DELETE" },
    ),
  removeBotFromServer: (botId: number, serverId: number) =>
    request<void>(`/bots/${botId}/servers/${serverId}`, { method: "DELETE" }),

  listChannels: (serverId: number) => request<Channel[]>(`/servers/${serverId}/channels`),
  createChannel: (serverId: number, name: string, type: ChannelType = "text") =>
    request<Channel>(`/servers/${serverId}/channels`, { method: "POST", body: JSON.stringify({ name, type }) }),
  updateChannel: (serverId: number, channelId: number, patch: { name?: string; topic?: string | null }) =>
    request<Channel>(`/servers/${serverId}/channels/${channelId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  deleteChannel: (serverId: number, channelId: number) =>
    request<void>(`/servers/${serverId}/channels/${channelId}`, { method: "DELETE" }),

  listMessages: (channelId: number, limit = 50, cursor?: string | null) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cursor) params.set("cursor", cursor);
    return request<MessagePage>(`/channels/${channelId}/messages?${params.toString()}`);
  },
  sendMessage: (
    channelId: number,
    content: string,
    clientId: string,
    replyToEventId?: string,
  ) =>
    request<Message>(`/channels/${channelId}/messages`, {
      method: "POST",
      body: JSON.stringify({
        content,
        client_id: clientId,
        reply_to_event_id: replyToEventId,
      }),
    }),
  deleteMessage: (channelId: number, eventId: string) =>
    request<void>(`/channels/${channelId}/messages/${encodeURIComponent(eventId)}`, { method: "DELETE" }),
  editMessage: (channelId: number, eventId: string, content: string) =>
    request<Message>(`/channels/${channelId}/messages/${encodeURIComponent(eventId)}`, {
      method: "PATCH",
      body: JSON.stringify({ content }),
    }),
  toggleReaction: (channelId: number, eventId: string, emoji: string) =>
    request<MessageReactionUpdate>(
      `/channels/${channelId}/messages/${encodeURIComponent(eventId)}/reactions`,
      { method: "PUT", body: JSON.stringify({ emoji }) },
    ),
  searchMessages: (channelId: number, query: string, userId?: number | null) => {
    const params = new URLSearchParams({ q: query });
    if (userId) params.set("user_id", String(userId));
    return request<Message[]>(
      `/channels/${channelId}/messages/search?${params.toString()}`,
    );
  },
  listPinnedMessages: (channelId: number) =>
    request<PinnedMessages>(`/channels/${channelId}/messages/pins`),
  pinMessage: (channelId: number, eventId: string) =>
    request<void>(
      `/channels/${channelId}/messages/${encodeURIComponent(eventId)}/pin`,
      { method: "PUT" },
    ),
  unpinMessage: (channelId: number, eventId: string) =>
    request<void>(
      `/channels/${channelId}/messages/${encodeURIComponent(eventId)}/pin`,
      { method: "DELETE" },
    ),
  createAiConversation: (title: string) =>
    request<AiConversation>("/ai/conversations", {
      method: "POST",
      body: JSON.stringify({ title }),
      timeoutMs: 8_000,
    }),
  sendAiMessage: (conversationId: number, content: string, idempotencyKey: string) =>
    request<AiJob>(`/ai/conversations/${conversationId}/messages`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ content }),
      timeoutMs: 8_000,
    }),
  getAiJob: (jobId: number) =>
    request<AiJob>(`/ai/jobs/${jobId}`, {
      retry: false,
      timeoutMs: 5_000,
    }),
  cancelAiJob: (jobId: number) =>
    request<AiJob>(`/ai/jobs/${jobId}/cancel`, {
      method: "POST",
      timeoutMs: 5_000,
    }),
  uploadAttachment: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Attachment>("/attachments", { method: "POST", body: form });
  },
};
