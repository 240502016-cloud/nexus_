import type {
  Claim,
  HiddenRoleGameResult,
  LegalAction,
  PlayerId,
  PrivatePlayerView,
  PublicGameView,
  RoundResult,
  Vote,
} from "./state-contract";

export interface CreateHiddenRoleGameRequest {
  serverId: number;
  channelId: number;
  theme: "ARCANE_ARCHIVE" | "ORBITAL_EMBASSY" | "CURSED_MUSEUM";
  interface: "WEB" | "DISCORD";
  loreMode: "OFF" | "CONSENTED_COSMETIC";
  discussionSeconds: 60 | 90 | 120;
}

export interface HiddenRoleRoomResponse {
  roomId: string;
  status: "LOBBY" | "ACTIVE" | "COMPLETED" | "CANCELLED";
  hostPlayerId: PlayerId;
  playerCount: 1 | 2 | 3;
  lobbyRevision: number;
  inviteCode?: string;
  inviteExpiresAt?: string;
  gameId?: string;
}

export interface JoinRoomRequest {
  inviteCode: string;
}

export interface SetReadyRequest {
  ready: boolean;
}

export interface StartGameRequest {
  expectedLobbyRevision: number;
}

export interface SubmitActionRequest {
  actionId: string;
  parameters: Record<string, string | number | boolean | string[]>;
  actionToken: string;
  expectedRevision: number;
}

export interface CreateClaimRequest {
  kind: "EVIDENCE" | "ACCUSATION";
  subjectOptionId?: string;
  proposition?: string;
  targetPlayerId?: PlayerId;
  guessedOffice?: string;
  guessedMandate?: string;
  flavorText?: string;
  reputationStake: 0 | 1;
  claimToken: string;
  expectedRevision: number;
}

export interface CastVoteRequest {
  roundId: string;
  optionId: string;
  voteToken: string;
  expectedRevision: number;
}

export interface FinalDeductionRequest {
  officeByPlayer: Record<PlayerId, string>;
  mandateByPlayer: Record<PlayerId, string>;
  deductionToken: string;
  expectedRevision: number;
}

export interface CommandAcceptedResponse {
  accepted: true;
  commandId: string;
  appliedRevision: number;
  eventIds: string[];
}

export interface WsTicketResponse {
  ticket: string;
  expiresAt: string;
}

export interface EventEnvelope<TType extends string, TPayload> {
  eventId: string;
  gameId: string;
  sequence: number;
  revision: number;
  type: TType;
  occurredAt: string;
  payload: TPayload;
}

export type HiddenRoleRealtimeEvent =
  | EventEnvelope<"room.updated", { room: HiddenRoleRoomResponse }>
  | EventEnvelope<"player.connection", { playerId: PlayerId; connected: boolean }>
  | EventEnvelope<"host.changed", { previousHostPlayerId: PlayerId; hostPlayerId: PlayerId }>
  | EventEnvelope<"game.started", { publicState: PublicGameView }>
  | EventEnvelope<"public.snapshot", { state: PublicGameView; reason: "INITIAL" | "RECONNECT" | "GAP" }>
  | EventEnvelope<"private.snapshot", { state: PrivatePlayerView; reason: "INITIAL" | "RECONNECT" | "GAP" }>
  | EventEnvelope<"private.role_delivered", { playerId: PlayerId; privateState: PrivatePlayerView }>
  | EventEnvelope<"round.started", { roundNumber: number; publicState: PublicGameView }>
  | EventEnvelope<"phase.changed", { phase: string; deadlineAt: string; legalActions?: LegalAction[] }>
  | EventEnvelope<"private.clue_delivered", { playerId: PlayerId; privateState: PrivatePlayerView }>
  | EventEnvelope<"claim.created", { claim: Claim }>
  | EventEnvelope<"vote.received", { submittedVoteCount: number }>
  | EventEnvelope<"private.vote_receipt", { playerId: PlayerId; vote: Vote }>
  | EventEnvelope<"round.resolved", { result: RoundResult; publicState: PublicGameView }>
  | EventEnvelope<"deduction.requested", { deadlineAt: string; legalAction: LegalAction }>
  | EventEnvelope<"game.completed", {
      groupOutcome: string;
      winnerPlayerId: PlayerId;
      totalByPlayer: Record<PlayerId, number>;
      revealPending: true;
    }>
  | EventEnvelope<"roles.revealed", { result: HiddenRoleGameResult; recapPending: boolean }>
  | EventEnvelope<"recap.ready", { text: string; fallbackUsed: boolean; sourceEventIds: string[] }>
  | EventEnvelope<"resync.required", { currentRevision: number; currentSequence: number }>
  | EventEnvelope<"error", { code: string; message: string }>;

export type ClientSocketMessage =
  | { type: "hello"; lastSeenSequence: number; lastSeenRevision: number }
  | { type: "ack"; lastSeenSequence: number }
  | { type: "ping"; sentAt: string };

/**
 * REST endpoint map
 *
 * POST   /api/hidden-role/rooms                         create room + one-time code
 * POST   /api/hidden-role/rooms/join                    join; same server required
 * POST   /api/hidden-role/rooms/:roomId/ready           ready/unready
 * POST   /api/hidden-role/rooms/:roomId/start           exactly 3 ready players
 * POST   /api/hidden-role/rooms/:roomId/rotate-invite   revoke/rotate lobby code
 * GET    /api/hidden-role/games/:gameId/public          participant-safe public view
 * GET    /api/hidden-role/games/:gameId/private/me      authenticated self only
 * POST   /api/hidden-role/games/:gameId/actions         generic listed action
 * POST   /api/hidden-role/games/:gameId/claims          structured public claim
 * POST   /api/hidden-role/games/:gameId/votes           sealed self vote
 * POST   /api/hidden-role/games/:gameId/deductions      sealed final mapping
 * POST   /api/hidden-role/games/:gameId/ws-ticket       single-use 60s socket ticket
 * GET    /api/hidden-role/games/:gameId/events?after=N  authorized replay/poll fallback
 * GET    /api/hidden-role/games/:gameId/recap           post-reveal result/recap
 * POST   /internal/hidden-role/games/:gameId/resolve    scheduler only
 * POST   /internal/hidden-role/clues/:clueId/deliver    engine worker only
 * POST   /internal/hidden-role/games/:gameId/end        deterministic resolver only
 * GET    /ws/hidden-role/:gameId?ticket=...             personalized event stream
 */

export const REALTIME_POLICY = {
  websocketTicketTtlSeconds: 60,
  heartbeatSeconds: 20,
  staleConnectionSeconds: 60,
  disconnectedPhaseGraceSeconds: 60,
  eventReplayLimit: 300,
  pollingFallbackSeconds: 3,
  voteDeadlineDefaultSeconds: 30,
  finalDeductionDeadlineSeconds: 90,
} as const;

/**
 * Discord adapter
 *
 * - Public crisis/claim/result events go to the bound server channel.
 * - Roles, mandates, objectives, clues, vote receipts and deductions use DM only.
 * - A player cannot mark ready until the bot verifies DM delivery. Ephemeral messages
 *   may explain errors but are not the primary secret channel.
 * - Component interaction IDs become Idempotency-Key values. Buttons/selects submit
 *   the same REST commands as the web UI; the bot never owns game state.
 * - Raw Discord message text is not a mechanical action. Natural-language parsing
 *   proposes a structured action and requires a confirm button.
 */
