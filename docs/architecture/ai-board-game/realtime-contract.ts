import type { Action, GameResult, GameView, PlayerId } from "./state-contract";

/**
 * Mutations use authenticated REST with Idempotency-Key and expectedRevision.
 * A game-scoped WebSocket carries ordered, privacy-filtered events only.
 */

export interface CreateGameRoomRequest {
  serverId: number;
  channelId: number;
  theme: "ARCANE_RUINS" | "SPACE_WRECK" | "CURSED_CARNIVAL";
  loreMode: "OFF" | "CONSENTED_FLAVOR";
  narrationStyle: "COMPACT" | "DRAMATIC" | "PLAYFUL";
}

export interface GameRoomResponse {
  roomId: string;
  serverId: number;
  channelId: number;
  status: "LOBBY" | "ACTIVE" | "COMPLETED" | "CANCELLED";
  hostPlayerId: PlayerId;
  playerCount: 1 | 2 | 3;
  /** Returned only from create/rotate endpoints; never persisted as plaintext. */
  inviteCode?: string;
  inviteExpiresAt?: string;
  gameId?: string;
}

export interface JoinGameRoomRequest {
  inviteCode: string;
}

export interface SetReadyRequest {
  ready: boolean;
}

export interface StartGameRequest {
  expectedLobbyRevision: number;
}

export interface SelectObjectiveRequest {
  objectiveId: string;
  expectedRevision: number;
}

export interface SubmitGameActionRequest {
  actionId: string;
  actionToken: string;
  expectedRevision: number;
  parameters: Record<string, string | number | boolean | string[]>;
}

export interface SubmitGameActionResponse {
  accepted: true;
  commandId: string;
  appliedRevision: number;
  publicEventIds: string[];
  privateEventIds: string[];
}

export interface WsTicketResponse {
  ticket: string;
  expiresAt: string;
}

export interface GameEventEnvelope<TType extends string, TPayload> {
  eventId: string;
  gameId: string;
  revision: number;
  sequence: number;
  type: TType;
  occurredAt: string;
  payload: TPayload;
}

export type GameRealtimeEvent =
  | GameEventEnvelope<"room.updated", { room: GameRoomResponse }>
  | GameEventEnvelope<"player.joined", { playerId: PlayerId; seat: 0 | 1 | 2 }>
  | GameEventEnvelope<"player.ready", { playerId: PlayerId; ready: boolean }>
  | GameEventEnvelope<"player.connection", { playerId: PlayerId; connected: boolean }>
  | GameEventEnvelope<"host.changed", { previousHostPlayerId: PlayerId; hostPlayerId: PlayerId }>
  | GameEventEnvelope<"game.started", { view: GameView }>
  | GameEventEnvelope<"state.snapshot", { view: GameView; reason: "INITIAL" | "RECONNECT" | "GAP" }>
  | GameEventEnvelope<"turn.started", {
      activePlayerId: PlayerId;
      round: number;
      deadlineAt: string;
      legalActions: Action[];
    }>
  | GameEventEnvelope<"action.resolved", {
      actorPlayerId: PlayerId;
      actionKind: string;
      mechanicalSummary: string;
      changedPaths: string[];
    }>
  | GameEventEnvelope<"choice.requested", {
      choiceId: string;
      playerIds: PlayerId[];
      sealed: boolean;
      deadlineAt: string;
    }>
  | GameEventEnvelope<"choice.resolved", { choiceId: string; publicResult: Record<string, unknown> }>
  | GameEventEnvelope<"private.objectives", { playerId: PlayerId; objectiveIds: string[] }>
  | GameEventEnvelope<"private.hand", { playerId: PlayerId; cardIds: string[] }>
  | GameEventEnvelope<"narration.ready", {
      sourceEventIds: string[];
      text: string;
      fallbackUsed: boolean;
    }>
  | GameEventEnvelope<"game.ended", { result: GameResult }>
  | GameEventEnvelope<"resync.required", { currentRevision: number }>
  | GameEventEnvelope<"error", { code: string; message: string }>;

export interface ClientHello {
  type: "hello";
  lastSeenSequence: number;
  lastSeenRevision: number;
}

export interface ClientAck {
  type: "ack";
  lastSeenSequence: number;
}

export interface ClientPing {
  type: "ping";
  sentAt: string;
}

export type ClientGameSocketMessage = ClientHello | ClientAck | ClientPing;

/**
 * Endpoint map
 *
 * POST   /api/game-rooms                         create room + one-time invite code
 * POST   /api/game-rooms/join                    join by code; server membership required
 * POST   /api/game-rooms/:roomId/ready           ready/unready
 * POST   /api/game-rooms/:roomId/start           host starts only when exactly 3 are ready
 * POST   /api/game-rooms/:roomId/rotate-invite   revoke/rotate code before start
 * DELETE /api/game-rooms/:roomId/players/me      leave lobby; active games become disconnected
 * GET    /api/games/:gameId                      privacy-filtered current view
 * GET    /api/games/:gameId/events?after=N       ordered catch-up / polling fallback
 * POST   /api/games/:gameId/objectives/select    select one offered secret objective
 * POST   /api/games/:gameId/actions              Idempotency-Key required
 * POST   /api/games/:gameId/ws-ticket            60-second single-use WebSocket ticket
 * GET    /ws/games/:gameId?ticket=...             personalized event stream
 */

export interface ReconnectPolicy {
  websocketTicketTtlSeconds: 60;
  heartbeatSeconds: 20;
  staleConnectionSeconds: 60;
  activeTurnDisconnectGraceSeconds: 90;
  eventReplayLimit: 500;
  pollingFallbackSeconds: 3;
}

export const RECONNECT_POLICY: ReconnectPolicy = {
  websocketTicketTtlSeconds: 60,
  heartbeatSeconds: 20,
  staleConnectionSeconds: 60,
  activeTurnDisconnectGraceSeconds: 90,
  eventReplayLimit: 500,
  pollingFallbackSeconds: 3,
};
