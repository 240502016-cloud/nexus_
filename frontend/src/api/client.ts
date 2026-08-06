// Core API'ye konuşan ince bir fetch sarmalayıcısı.
// Geliştirmede /api -> vite.config.ts proxy'si üzerinden http://localhost:8000'e yönlenir.

import type {
  AiConversation,
  AiJob,
  Bot,
  BoardGameView,
  Attachment,
  Channel,
  ChannelType,
  CommentaryHistory,
  CommentaryIntensity,
  CommentarySession,
  CommentatorProfile,
  DirectConversation,
  EscapeRoomView,
  Friend,
  FriendRequest,
  FriendRequestList,
  LoginResponse,
  LoreCandidate,
  LoreEntry,
  Member,
  Message,
  MessagePage,
  MessageReactionUpdate,
  MemeCandidateResponse,
  MemeJob,
  MemeMomentType,
  GeneratedMeme,
  HighlightCandidate,
  HighlightRecording,
  HiddenRoleGameView,
  RenderedHighlight,
  RoastProfile,
  RoastRound,
  RoastSession,
  RoastTopic,
  PinnedMessages,
  PluginManifest,
  PublicUser,
  Server,
  ServerInvite,
  ServerInviteList,
  ServerJoinCode,
  SharedStoryView,
  StorySafetyProfile,
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

function readableErrorDetail(value: unknown, fallback: string): string {
  if (typeof value === "string" && value.trim()) return value;
  if (Array.isArray(value)) {
    const messages = value
      .map((item) => {
        if (!item || typeof item !== "object") return null;
        const issue = item as { loc?: unknown; msg?: unknown };
        if (typeof issue.msg !== "string") return null;
        const field = Array.isArray(issue.loc) ? issue.loc.filter((part) => part !== "body").join(".") : "";
        return field ? `${field}: ${issue.msg}` : issue.msg;
      })
      .filter((message): message is string => Boolean(message));
    if (messages.length) return messages.join(" · ");
  }
  if (value && typeof value === "object") {
    const objectValue = value as { message?: unknown; detail?: unknown };
    if (typeof objectValue.message === "string") return objectValue.message;
    if (typeof objectValue.detail === "string") return objectValue.detail;
  }
  return fallback;
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
        detail = readableErrorDetail(body.detail, detail);
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

async function requestBlob(path: string): Promise<Blob> {
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(apiUrl(path), { headers });
  if (!response.ok) {
    let detail = response.statusText || "Dosya alınamadı";
    try {
      const body = await response.json();
      detail = readableErrorDetail(body.detail, detail);
    } catch {
      // Binary olmayan hata gövdesi JSON değilse statusText yeterlidir.
    }
    throw new ApiError(response.status, detail);
  }
  return response.blob();
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
  updateProfile: (patch: {
    display_name?: string | null;
    email?: string;
    current_password?: string;
  }) =>
    request<User>("/users/me", { method: "PATCH", body: JSON.stringify(patch) }),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<LoginResponse>("/users/me/password", {
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
  listLoreCandidates: (serverId: number) =>
    request<LoreCandidate[]>(`/servers/${serverId}/party-lore/candidates`),
  listLoreEntries: (serverId: number) =>
    request<LoreEntry[]>(`/servers/${serverId}/party-lore/entries`),
  createLoreCandidate: (
    serverId: number,
    payload: {
      title: string;
      summary: string;
      participant_ids: number[];
      category: string;
      sensitivity: "low" | "medium" | "high";
      allowed_modules: string[];
    },
    idempotencyKey: string,
  ) => request<LoreCandidate>(`/servers/${serverId}/party-lore/candidates`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(payload),
  }),
  reviewLoreCandidate: (candidateId: string, decision: "approved" | "rejected") =>
    request<LoreCandidate>(`/party-lore/candidates/${candidateId}/review`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    }),
  deleteLoreEntry: (loreId: string) =>
    request<void>(`/party-lore/entries/${loreId}`, { method: "DELETE" }),
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
  listCommentatorProfiles: (serverId: number) =>
    request<CommentatorProfile[]>(`/servers/${serverId}/commentary/profiles`),
  getActiveCommentarySession: (serverId: number) =>
    request<CommentarySession | null>(`/servers/${serverId}/commentary/sessions/active`),
  createCommentarySession: (
    serverId: number,
    payload: {
      game_key: string;
      player_ids: number[];
      profile_key: string;
      intensity: CommentaryIntensity;
      text_to_speech_enabled: boolean;
      output_channel_id: number | null;
    },
    idempotencyKey: string,
  ) =>
    request<CommentarySession>(`/servers/${serverId}/commentary/sessions`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    }),
  updateCommentarySession: (
    sessionId: string,
    patch: {
      expected_revision: number;
      profile_key?: string;
      intensity?: CommentaryIntensity;
      silent_mode?: boolean;
      current_tone?: string;
    },
  ) =>
    request<CommentarySession>(`/commentary/sessions/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  postCommentatorEvent: (
    sessionId: string,
    payload: {
      schema_version: "1.0";
      event_id: string;
      source: "MANUAL";
      occurred_at: string;
      category: string;
      actor_player_ids: number[];
      target_player_ids: number[];
      game: { game_key: string };
      importance: number;
      confidence: number;
      summary: string;
      emotional_tone: string;
      attributes: Record<string, unknown>;
    },
  ) =>
    request<{ event_id: string; accepted: true; state: "PENDING" | "DEDUPLICATED" | "FILTERED" }>(
      `/commentary/sessions/${sessionId}/events`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  getCommentaryHistory: (sessionId: string) =>
    request<CommentaryHistory>(`/commentary/sessions/${sessionId}/history`),
  submitCommentaryFeedback: (
    commentaryId: string,
    feedbackType: "FUNNY" | "NOT_FUNNY" | "TOO_HARSH" | "REPETITIVE" | "WRONG_CONTEXT",
  ) =>
    request<void>(`/commentary/commentary/${commentaryId}/feedback`, {
      method: "POST",
      body: JSON.stringify({ feedback_type: feedbackType }),
    }),
  endCommentarySession: (sessionId: string, expectedRevision: number) =>
    request<CommentarySession>(`/commentary/sessions/${sessionId}/end`, {
      method: "POST",
      body: JSON.stringify({ expected_revision: expectedRevision }),
    }),
  createMemeJob: (
    serverId: number,
    payload: {
      event: {
        schema_version: "1.0";
        event_id: string;
        server_id: number;
        source: "MANUAL";
        occurred_at: string;
        moment_type: MemeMomentType;
        actor_player_ids: number[];
        target_player_ids: number[];
        game: { game_key: string };
        summary: string;
        setup?: string;
        payoff?: string;
        importance: number;
        confidence: number;
        facts: Array<{ key: "durationSeconds" | "attemptCount" | "itemsLost" | "healthRemaining" | "teamSize"; value: string | number | boolean }>;
      };
      preferred_formats: string[];
      desired_harshness: number;
    },
    idempotencyKey: string,
  ) =>
    request<MemeJob>(`/servers/${serverId}/memes/jobs`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    }),
  getMemeCandidates: (jobId: string) =>
    request<MemeCandidateResponse>(`/memes/jobs/${jobId}/candidates`),
  renderMeme: (
    jobId: string,
    candidateId: string,
    captionOverrides: Record<string, string> = {},
  ) =>
    request<GeneratedMeme>(`/memes/jobs/${jobId}/render`, {
      method: "POST",
      body: JSON.stringify({
        candidate_id: candidateId,
        caption_overrides: captionOverrides,
        output_format: "PNG",
      }),
    }),
  getMemeAsset: (assetUrl: string) => requestBlob(assetUrl),
  submitMemeFeedback: (
    memeId: string,
    feedbackType: "FUNNY" | "FORCED" | "TOO_HARSH" | "REPETITIVE" | "WRONG_CONTEXT" | "SAVE",
  ) =>
    request<void>(`/memes/${memeId}/feedback`, {
      method: "POST",
      body: JSON.stringify({ feedback_type: feedbackType }),
    }),
  deleteMeme: (memeId: string) =>
    request<void>(`/memes/${memeId}`, { method: "DELETE" }),
  createHighlightRecording: (
    serverId: number,
    payload: {
      source_type: "MANUAL_UPLOAD" | "OBS_REPLAY_BUFFER";
      original_filename: string;
      byte_size: number;
      content_type: "video/mp4" | "video/x-matroska";
    },
    idempotencyKey: string,
  ) =>
    request<HighlightRecording>(`/servers/${serverId}/highlight/recordings`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    }),
  uploadHighlightContent: async (uploadUrl: string, file: File) => {
    const headers: Record<string, string> = { "Content-Type": file.type || "application/octet-stream" };
    if (token) headers.Authorization = `Bearer ${token}`;
    const response = await fetch(apiUrl(uploadUrl), { method: "PUT", headers, body: file });
    if (!response.ok) {
      let detail = response.statusText || "Video yüklenemedi";
      try {
        const body = await response.json();
        detail = readableErrorDetail(body.detail, detail);
      } catch {
        // JSON olmayan hata gövdesinde statusText kullanılır.
      }
      throw new ApiError(response.status, detail);
    }
    return response.json() as Promise<HighlightRecording>;
  },
  getHighlightRecording: (recordingId: string) =>
    request<HighlightRecording>(`/highlight/recordings/${recordingId}`),
  createHighlightMarker: (
    recordingId: string,
    payload: {
      schema_version: "1.0";
      marker_id: string;
      source: "MANUAL";
      offset_ms: number;
      category_hint: "SKILL" | "COMEDY" | "FAILURE" | "CHAOS" | "LORE_WORTHY";
      participant_player_ids: number[];
      summary: string;
      manual_priority: 1;
    },
  ) =>
    request<HighlightCandidate>(`/highlight/recordings/${recordingId}/markers`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  renderHighlight: (
    candidateId: string,
    payload: { start_ms: number; end_ms: number; title_override: string; variant: "LANDSCAPE" },
  ) =>
    request<RenderedHighlight>(`/highlight/candidates/${candidateId}/render`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getRenderedHighlight: (highlightId: string) =>
    request<RenderedHighlight>(`/highlight/renders/${highlightId}`),
  getHighlightAsset: (assetUrl: string) => requestBlob(assetUrl),
  getRoastProfile: (serverId: number) =>
    request<RoastProfile>(`/servers/${serverId}/roast-battle/profile/me`),
  updateRoastProfile: (
    serverId: number,
    payload: {
      roast_enabled: boolean;
      maximum_intensity: number;
      allowed_topics: RoastTopic[];
      allow_party_lore: boolean;
      allow_highlights: boolean;
      allow_recent_failures: boolean;
      blocked_terms: string[];
    },
  ) =>
    request<RoastProfile>(`/servers/${serverId}/roast-battle/profile/me`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  getActiveRoastSession: (serverId: number) =>
    request<RoastSession | null>(`/servers/${serverId}/roast-battle/sessions/active`),
  createRoastSession: (
    serverId: number,
    payload: { player_ids: number[]; requested_intensity: number },
    idempotencyKey: string,
  ) =>
    request<RoastSession>(`/servers/${serverId}/roast-battle/sessions`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    }),
  getRoastSession: (sessionId: string) =>
    request<RoastSession>(`/roast-battle/sessions/${sessionId}`),
  submitRoastConsent: (
    sessionId: string,
    decision: "READY" | "DECLINE" | "REVOKE",
    consentVersion: number,
  ) =>
    request<RoastSession>(`/roast-battle/sessions/${sessionId}/consent`, {
      method: "POST",
      body: JSON.stringify({ decision, consent_version: consentVersion }),
    }),
  getCurrentRoastRound: (sessionId: string) =>
    request<RoastRound | null>(`/roast-battle/sessions/${sessionId}/rounds/current`),
  startNextRoastRound: (sessionId: string) =>
    request<RoastRound>(`/roast-battle/sessions/${sessionId}/rounds/next`, {
      method: "POST",
    }),
  getRoastRound: (roundId: string) =>
    request<RoastRound>(`/roast-battle/rounds/${roundId}`),
  voteRoast: (candidateId: string, vote: "FUNNY" | "OKAY" | "PASS") =>
    request<{ candidate_id: string; vote: string; score_contribution: number }>(
      `/roast-battle/candidates/${candidateId}/vote`,
      { method: "PUT", body: JSON.stringify({ vote }) },
    ),
  getActiveBoardGame: (serverId: number) =>
    request<BoardGameView | null>(`/servers/${serverId}/board-game/sessions/active`),
  createBoardGame: (
    serverId: number,
    payload: { player_ids: number[]; ai_players: number; theme: "ARCANE_RUINS" | "SPACE_WRECK" | "CURSED_CARNIVAL" },
    idempotencyKey: string,
  ) =>
    request<BoardGameView>(`/servers/${serverId}/board-game/sessions`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    }),
  getBoardGame: (sessionId: string) =>
    request<BoardGameView>(`/board-game/sessions/${sessionId}`),
  submitBoardGameAction: (
    sessionId: string,
    payload: { action_id: string; action_token: string; expected_revision: number },
    idempotencyKey: string,
  ) =>
    request<BoardGameView>(`/board-game/sessions/${sessionId}/actions`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    }),
  getActiveHiddenRoleGame: (serverId: number) =>
    request<HiddenRoleGameView | null>(`/servers/${serverId}/hidden-role/sessions/active`),
  createHiddenRoleGame: (serverId: number, playerIds: number[], aiPlayers: number, idempotencyKey: string) =>
    request<HiddenRoleGameView>(`/servers/${serverId}/hidden-role/sessions`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ player_ids: playerIds, ai_players: aiPlayers }),
    }),
  getHiddenRoleGame: (sessionId: string) =>
    request<HiddenRoleGameView>(`/hidden-role/sessions/${sessionId}`),
  submitHiddenRoleClaim: (
    sessionId: string,
    payload: { subject_option_id: "A" | "B" | "C"; proposition: string; flavor_text: string; action_token: string; expected_revision: number },
  ) => request<HiddenRoleGameView>(`/hidden-role/sessions/${sessionId}/claims`, { method: "POST", body: JSON.stringify(payload) }),
  submitHiddenRoleVote: (
    sessionId: string,
    payload: { option_id: "A" | "B" | "C"; action_token: string; expected_revision: number },
  ) => request<HiddenRoleGameView>(`/hidden-role/sessions/${sessionId}/votes`, { method: "POST", body: JSON.stringify(payload) }),
  submitHiddenRoleDeduction: (
    sessionId: string,
    payload: { office_by_key: Record<string, string>; mandate_by_key: Record<string, string>; action_token: string; expected_revision: number },
  ) => request<HiddenRoleGameView>(`/hidden-role/sessions/${sessionId}/deductions`, { method: "POST", body: JSON.stringify(payload) }),
  getStorySafetyProfile: (serverId: number) =>
    request<StorySafetyProfile>(`/servers/${serverId}/shared-story/safety/me`),
  updateStorySafetyProfile: (
    serverId: number,
    payload: Omit<StorySafetyProfile, "server_id" | "user_id" | "version" | "updated_at">,
  ) => request<StorySafetyProfile>(`/servers/${serverId}/shared-story/safety/me`, { method: "PUT", body: JSON.stringify(payload) }),
  getActiveSharedStory: (serverId: number) =>
    request<SharedStoryView | null>(`/servers/${serverId}/shared-story/sessions/active`),
  createSharedStory: (
    serverId: number,
    payload: { player_ids: number[]; ai_players: number; theme: "MYSTERY" | "SURVIVAL" | "FANTASY"; length: "SHORT" | "STANDARD" | "LONG"; use_party_lore: boolean },
    idempotencyKey: string,
  ) => request<SharedStoryView>(`/servers/${serverId}/shared-story/sessions`, { method: "POST", headers: { "Idempotency-Key": idempotencyKey }, body: JSON.stringify(payload) }),
  getSharedStory: (sessionId: string) => request<SharedStoryView>(`/shared-story/sessions/${sessionId}`),
  submitStoryAction: (
    sessionId: string,
    payload: { action_id: "INVESTIGATE" | "PROTECT" | "PRESS_ON"; action_token: string; expected_revision: number },
    idempotencyKey: string,
  ) => request<SharedStoryView>(`/shared-story/sessions/${sessionId}/actions`, { method: "POST", headers: { "Idempotency-Key": idempotencyKey }, body: JSON.stringify(payload) }),
  submitStoryVote: (
    sessionId: string,
    payload: { choice_id: "STABILIZE" | "REVEAL_PATH" | "PUSH_FORWARD"; action_token: string; expected_revision: number },
  ) => request<SharedStoryView>(`/shared-story/sessions/${sessionId}/votes`, { method: "POST", body: JSON.stringify(payload) }),
  getActiveEscapeRoom: (serverId: number) => request<EscapeRoomView | null>(`/servers/${serverId}/escape-room/sessions/active`),
  createEscapeRoom: (
    serverId: number,
    payload: { player_ids: number[]; ai_players: number; timer_mode: "RELAXED" | "STANDARD_45" | "CHALLENGE_30"; use_party_lore: boolean },
    idempotencyKey: string,
  ) => request<EscapeRoomView>(`/servers/${serverId}/escape-room/sessions`, { method: "POST", headers: { "Idempotency-Key": idempotencyKey }, body: JSON.stringify(payload) }),
  getEscapeRoom: (sessionId: string) => request<EscapeRoomView>(`/escape-room/sessions/${sessionId}`),
  submitEscapeAnswer: (
    sessionId: string,
    nodeId: string,
    payload: { answer: string; action_token: string; expected_revision: number },
    idempotencyKey: string,
  ) => request<{ validator_result: "CORRECT" | "INCORRECT" | "DUPLICATE"; node_id: string; view: EscapeRoomView }>(`/escape-room/sessions/${sessionId}/nodes/${nodeId}/answers`, { method: "POST", headers: { "Idempotency-Key": idempotencyKey }, body: JSON.stringify(payload) }),
  requestEscapeHint: (
    sessionId: string,
    nodeId: string,
    payload: { tier: number; action_token: string; expected_revision: number },
  ) => request<EscapeRoomView>(`/escape-room/sessions/${sessionId}/nodes/${nodeId}/hints`, { method: "POST", body: JSON.stringify(payload) }),
  uploadAttachment: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Attachment>("/attachments", { method: "POST", body: form });
  },
};
