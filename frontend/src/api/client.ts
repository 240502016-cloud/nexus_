// Core API'ye konuşan ince bir fetch sarmalayıcısı.
// Geliştirmede /api -> vite.config.ts proxy'si üzerinden http://localhost:8000'e yönlenir.

import type {
  Bot,
  Channel,
  ChannelType,
  LoginResponse,
  Member,
  Message,
  PluginManifest,
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
  if (init?.body && !(init.body instanceof URLSearchParams)) {
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

  myServers: () => request<Server[]>("/servers"),
  createServer: (name: string) =>
    request<Server>("/servers", { method: "POST", body: JSON.stringify({ name }) }),

  listMembers: (serverId: number) => request<Member[]>(`/servers/${serverId}/members`),
  addMember: (serverId: number, username: string) =>
    request<{ status: string }>(`/servers/${serverId}/members?username=${encodeURIComponent(username)}`, {
      method: "POST",
    }),

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

  listChannels: (serverId: number) => request<Channel[]>(`/servers/${serverId}/channels`),
  createChannel: (serverId: number, name: string, type: ChannelType = "text") =>
    request<Channel>(`/servers/${serverId}/channels`, { method: "POST", body: JSON.stringify({ name, type }) }),

  listMessages: (channelId: number, limit = 50) =>
    request<Message[]>(`/channels/${channelId}/messages?limit=${limit}`),
  sendMessage: (channelId: number, content: string) =>
    request<Message>(`/channels/${channelId}/messages`, { method: "POST", body: JSON.stringify({ content }) }),
};
