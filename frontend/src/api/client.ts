// Core API'ye konuşan ince bir fetch sarmalayıcısı.
// Geliştirmede /api -> vite.config.ts proxy'si üzerinden http://localhost:8000'e yönlenir.

import type {
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
  PluginManifest,
  PublicUser,
  Server,
  User,
} from "../types";

const BASE_URL = "/api";
const TOKEN_STORAGE_KEY = "nexus_token";

let token: string | null = localStorage.getItem(TOKEN_STORAGE_KEY);

export function getToken(): string | null {
  return token;
}

export function setToken(newToken: string | null): void {
  token = newToken;
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { ...(init?.headers as Record<string, string> | undefined) };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  // FormData ve URLSearchParams'ta Content-Type'ı tarayıcı belirler (multipart boundary vb.).
  if (init?.body && !(init.body instanceof URLSearchParams) && !(init.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(`${BASE_URL}${path}`, { ...init, headers });

  if (!response.ok) {
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

export const coreApi = {
  health: () => request<{ status: string }>("/health"),

  voiceIceServers: () => request<{ ice_servers: RTCIceServer[]; expires_at: number }>("/voice/ice-servers"),

  login: (username: string, password: string) => {
    const body = new URLSearchParams({ username, password });
    return request<LoginResponse>("/auth/login", { method: "POST", body });
  },

  register: (username: string, email: string, password: string) =>
    request<User>("/users", { method: "POST", body: JSON.stringify({ username, email, password }) }),

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
    }),
  acceptFriendRequest: (friendshipId: number) =>
    request<Friend>(`/friends/requests/${friendshipId}/accept`, { method: "POST" }),
  removeFriendship: (friendshipId: number) =>
    request<void>(`/friends/${friendshipId}`, { method: "DELETE" }),

  listDirectConversations: () => request<DirectConversation[]>("/direct/conversations"),
  listDirectMessages: (conversationId: number, limit = 50, cursor?: string | null) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cursor) params.set("cursor", cursor);
    return request<MessagePage>(
      `/direct/conversations/${conversationId}/messages?${params.toString()}`,
    );
  },
  sendDirectMessage: (conversationId: number, content: string, clientId: string) =>
    request<Message>(`/direct/conversations/${conversationId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content, client_id: clientId }),
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
    request<{ status: string }>(`/servers/${serverId}/members`, {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
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
  sendMessage: (channelId: number, content: string, clientId: string) =>
    request<Message>(`/channels/${channelId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content, client_id: clientId }),
    }),
  deleteMessage: (channelId: number, eventId: string) =>
    request<void>(`/channels/${channelId}/messages/${encodeURIComponent(eventId)}`, { method: "DELETE" }),
  editMessage: (channelId: number, eventId: string, content: string) =>
    request<Message>(`/channels/${channelId}/messages/${encodeURIComponent(eventId)}`, {
      method: "PATCH",
      body: JSON.stringify({ content }),
    }),
  uploadAttachment: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Attachment>("/attachments", { method: "POST", body: form });
  },
};
