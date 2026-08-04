import type {
  HintTier,
  PlayerId,
  PrivatePlayerView,
  PublicEscapeRoomView,
  PublicItemView,
  PuzzleStatus,
  SessionStatus,
  TimerState,
} from "./state-contract";
import type { AnswerInterpretation, SubmissionValue, ValidationResult } from "./validation-contract";

export interface CreateEscapeSessionRequest {
  serverId: number;
  channelId: number;
  timerMode: "RELAXED" | "STANDARD_45" | "CHALLENGE_30";
  difficulty: 1 | 2 | 3 | 4 | 5;
  loreMode: "OFF" | "CONSENTED_COSMETIC";
  accessibilityMode: "STANDARD" | "EXTENDED_TIME" | "NO_SIMULTANEOUS_PRESSURE";
}

export interface EscapeLobbyResponse {
  sessionId: string;
  status: SessionStatus;
  hostPlayerId: PlayerId;
  playerCount: 1 | 2 | 3;
  readyCount: number;
  revision: number;
  roomCode?: string;
  roomCodeExpiresAt?: string;
}

export interface JoinEscapeSessionRequest {
  roomCode: string;
}

export interface SetEscapeReadyRequest {
  ready: boolean;
  privateDeliveryConfirmed: boolean;
}

export interface SubmitEscapeAnswerRequest {
  puzzleId: string;
  answer: SubmissionValue;
  answerToken: string;
  expectedRevision: number;
}

export interface InterpretEscapeAnswerRequest {
  puzzleId: string;
  freeText: string;
  expectedRevision: number;
}

export interface InspectObjectRequest {
  objectId: string;
  focusTag?: string;
  actionToken: string;
  expectedRevision: number;
}

export interface UseItemRequest {
  itemInstanceId: string;
  targetObjectId: string;
  actionToken: string;
  expectedRevision: number;
}

export interface CombineItemsRequest {
  itemInstanceIds: string[];
  recipeToken: string;
  expectedRevision: number;
}

export interface RequestHintRequest {
  puzzleId: string;
  requestedTier: HintTier;
  hintToken: string;
  expectedRevision: number;
}

export interface FinalAssistConsentRequest {
  hintRequestId: string;
  consent: boolean;
  expectedRevision: number;
}

export interface RecordObservationRequest {
  text: string;
  linkedObjectIds: string[];
  visibility: "PUBLIC" | "SELF";
  assumptionTag?: string;
  observationToken: string;
  expectedRevision: number;
}

export interface SubmitSimultaneousInputRequest {
  puzzleId: string;
  windowId: string;
  input: string;
  inputToken: string;
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

export interface EscapeEventEnvelope<TType extends string, TPayload> {
  eventId: string;
  sessionId: string;
  sequence: number;
  revision: number;
  type: TType;
  occurredAt: string;
  payload: TPayload;
}

export type EscapeRoomRealtimeEvent =
  | EscapeEventEnvelope<"lobby.updated", { lobby: EscapeLobbyResponse }>
  | EscapeEventEnvelope<"player.connection", { playerId: PlayerId; connected: boolean }>
  | EscapeEventEnvelope<"host.changed", { previousHostPlayerId: PlayerId; hostPlayerId: PlayerId }>
  | EscapeEventEnvelope<"session.started", { view: PublicEscapeRoomView }>
  | EscapeEventEnvelope<"public.snapshot", { view: PublicEscapeRoomView; reason: "INITIAL" | "RECONNECT" | "GAP" | "RESUME" }>
  | EscapeEventEnvelope<"private.snapshot", { view: PrivatePlayerView; reason: "INITIAL" | "RECONNECT" | "GAP" | "RESUME" }>
  | EscapeEventEnvelope<"private.clue", { playerId: PlayerId; clueId: string; renderedText: string }>
  | EscapeEventEnvelope<"object.changed", { objectId: string; publicState: string }>
  | EscapeEventEnvelope<"private.object_changed", { playerId: PlayerId; objectId: string; state: Record<string, unknown> }>
  | EscapeEventEnvelope<"puzzle.available", { puzzleId: string; title: string; assignedPlayerIds: PlayerId[] }>
  | EscapeEventEnvelope<"puzzle.progress", { puzzleId: string; status: PuzzleStatus; publicProgressCode: string }>
  | EscapeEventEnvelope<"attempt.received", { puzzleId: string; playerId: PlayerId; result: "CORRECT" | "INCORRECT" | "INVALID_FORMAT" | "RATE_LIMITED" }>
  | EscapeEventEnvelope<"private.attempt_result", {
      playerId: PlayerId;
      puzzleId: string;
      result: Omit<ValidationResult, "normalizedAnswerHash" | "committedEffectIds">;
    }>
  | EscapeEventEnvelope<"answer.interpreted", { playerId: PlayerId; puzzleId: string; interpretation: AnswerInterpretation }>
  | EscapeEventEnvelope<"item.changed", { item: PublicItemView; holderType: "SHARED" }>
  | EscapeEventEnvelope<"private.item_changed", { playerId: PlayerId; item: Record<string, unknown> }>
  | EscapeEventEnvelope<"hint.available", { puzzleId: string; maximumTier: HintTier; reasonCode: string }>
  | EscapeEventEnvelope<"hint.requested", { hintRequestId: string; puzzleId: string; tier: HintTier; finalAssistConsentCount?: number }>
  | EscapeEventEnvelope<"hint.delivered", { puzzleId: string; tier: HintTier; text: string; penaltySeconds: number }>
  | EscapeEventEnvelope<"private.hint_delivered", { playerId: PlayerId; puzzleId: string; tier: HintTier; text: string }>
  | EscapeEventEnvelope<"simultaneous.window_opened", { puzzleId: string; windowId: string; deadlineAt: string }>
  | EscapeEventEnvelope<"simultaneous.progress", { puzzleId: string; submittedCount: number }>
  | EscapeEventEnvelope<"simultaneous.window_closed", { puzzleId: string; success: boolean }>
  | EscapeEventEnvelope<"observation.recorded", { observationId: string; playerId: PlayerId; text: string; linkedObjectIds: string[] }>
  | EscapeEventEnvelope<"private.observation_recorded", { playerId: PlayerId; observationId: string; text: string; linkedObjectIds: string[] }>
  | EscapeEventEnvelope<"timer.updated", { timer: TimerState }>
  | EscapeEventEnvelope<"session.paused", { timer: TimerState; snapshotRevision: number }>
  | EscapeEventEnvelope<"session.resumed", { timer: TimerState; snapshotRevision: number }>
  | EscapeEventEnvelope<"session.overtime", { timer: TimerState; gradeCap: string }>
  | EscapeEventEnvelope<"session.completed", { elapsedSeconds: number; grade: string; assistedSolveCount: number; optionalSolvedCount: number }>
  | EscapeEventEnvelope<"recap.ready", { text: string; fallbackUsed: boolean; sourceEventIds: string[] }>
  | EscapeEventEnvelope<"resync.required", { currentSequence: number; currentRevision: number }>
  | EscapeEventEnvelope<"error", { code: string; message: string }>;

export type ClientEscapeSocketMessage =
  | { type: "hello"; lastSeenSequence: number; lastSeenRevision: number }
  | { type: "ack"; lastSeenSequence: number }
  | { type: "ping"; sentAt: string };

/**
 * Endpoint map
 *
 * POST   /api/escape/sessions                         create lobby/code
 * POST   /api/escape/sessions/join                    join by expiring code
 * POST   /api/escape/sessions/:id/ready               ready + private delivery check
 * POST   /api/escape/sessions/:id/start               exactly 3 ready players
 * GET    /api/escape/sessions/:id                     spoiler-safe public view
 * GET    /api/escape/sessions/:id/private/me          self-private view
 * POST   /api/escape/sessions/:id/objects/inspect     inspect visible object
 * POST   /api/escape/sessions/:id/items/use           validated item/object use
 * POST   /api/escape/sessions/:id/items/combine       transactional exact recipe
 * POST   /api/escape/sessions/:id/answers/interpret   read-only free-text mapping
 * POST   /api/escape/sessions/:id/answers             strict deterministic submit
 * POST   /api/escape/sessions/:id/hints               request authorized tier
 * POST   /api/escape/sessions/:id/hints/consent       final-assist unanimous consent
 * POST   /api/escape/sessions/:id/observations        shared/private noncanonical note
 * POST   /api/escape/sessions/:id/simultaneous        player-bound input window
 * POST   /api/escape/sessions/:id/pause               host pause; timer/state checkpoint
 * POST   /api/escape/sessions/:id/resume              host resume latest revision
 * GET    /api/escape/sessions/:id/events?after=N      authorized replay/poll fallback
 * POST   /api/escape/sessions/:id/ws-ticket           60-second single-use ticket
 * GET    /ws/escape/:id?ticket=...                    personalized events
 * POST   /internal/escape/sessions/:id/timer          scheduler tick/overtime only
 * POST   /internal/escape/puzzles/:id/advance         validator resolver only
 */

export const ESCAPE_REALTIME_POLICY = {
  websocketTicketTtlSeconds: 60,
  heartbeatSeconds: 20,
  staleConnectionSeconds: 60,
  privateTakeoverGraceSeconds: 120,
  simultaneousWindowSeconds: 10,
  eventReplayLimit: 500,
  pollingFallbackSeconds: 3,
} as const;

/**
 * Host controls are deliberately narrow. Before start the host selects timer,
 * difficulty and accessibility and may rotate the invite. During play the host may
 * pause/resume only. The host cannot view private clues, validate answers, unlock
 * objects, advance nodes, grant items, alter the timer value or reveal solutions.
 */
