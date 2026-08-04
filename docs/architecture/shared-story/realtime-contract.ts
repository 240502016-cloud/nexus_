import type {
  ChapterProgress,
  EndingVector,
  PlayerId,
  PrivateStoryView,
  PublicCharacterView,
  PublicStoryView,
  StoryAction,
  StoryScene,
  ToneProfile,
} from "./state-contract";
import type { ActionInterpretation, SubmitStoryActionRequest } from "./action-contract";

export interface CreateStoryRequest {
  serverId: number;
  channelId: number;
  length: "SHORT_30" | "STANDARD_60" | "LONG_90";
  loreMode: "OFF" | "CONSENTED_FICTIONALIZED";
  responseSeconds: 60 | 90 | 120;
}

export interface SelectThemeRequest {
  theme: "FOGBOUND_FANTASY" | "ORBITAL_MYSTERY" | "LOST_EXPEDITION" | "TIME_LOOP_CITY";
  tone: ToneProfile;
  expectedRevision: number;
}

export interface CreateCharacterRequest {
  name: string;
  archetypeKey: string;
  pronouns: string;
  creationChoiceIds: string[];
  expectedRevision: number;
}

export interface StoryRoomResponse {
  storyId: string;
  status: string;
  hostPlayerId: PlayerId;
  playerCount: 1 | 2 | 3;
  readyCount: number;
  revision: number;
  inviteCode?: string;
  inviteExpiresAt?: string;
}

export interface InterpretActionRequest {
  freeText: string;
  expectedRevision: number;
}

export interface CastStoryVoteRequest {
  sceneId: string;
  choiceId: string;
  voteToken: string;
  expectedRevision: number;
}

export interface SafetyPauseRequest {
  reasonCategory?: "TONE" | "HORROR" | "VIOLENCE" | "ROMANCE" | "CONFLICT" | "PERSONAL_REFERENCE" | "OTHER";
  expectedRevision: number;
}

export interface PauseStoryRequest {
  expectedRevision: number;
}

export interface ResumeStoryRequest {
  expectedRevision: number;
}

export interface WsTicketResponse {
  ticket: string;
  expiresAt: string;
}

export interface StoryEventEnvelope<TType extends string, TPayload> {
  eventId: string;
  storyId: string;
  sequence: number;
  revision: number;
  type: TType;
  occurredAt: string;
  payload: TPayload;
}

export type SharedStoryRealtimeEvent =
  | StoryEventEnvelope<"room.updated", { room: StoryRoomResponse }>
  | StoryEventEnvelope<"player.connection", { playerId: PlayerId; connected: boolean }>
  | StoryEventEnvelope<"host.changed", { previousHostPlayerId: PlayerId; hostPlayerId: PlayerId }>
  | StoryEventEnvelope<"character.created", { character: PublicCharacterView }>
  | StoryEventEnvelope<"story.started", { view: PublicStoryView }>
  | StoryEventEnvelope<"public.snapshot", { view: PublicStoryView; reason: "INITIAL" | "RECONNECT" | "GAP" | "RESUME" }>
  | StoryEventEnvelope<"private.snapshot", { view: PrivateStoryView; reason: "INITIAL" | "RECONNECT" | "GAP" | "RESUME" }>
  | StoryEventEnvelope<"chapter.started", { chapterId: string; title: string; progress: ChapterProgress }>
  | StoryEventEnvelope<"scene.started", { scene: StoryScene; legalActions: StoryAction[] }>
  | StoryEventEnvelope<"spotlight.changed", { playerId: PlayerId; deadlineAt: string }>
  | StoryEventEnvelope<"private.information", { playerId: PlayerId; view: PrivateStoryView }>
  | StoryEventEnvelope<"action.interpreted", { playerId: PlayerId; interpretation: ActionInterpretation }>
  | StoryEventEnvelope<"action.resolved", {
      actionId: string;
      sceneId: string;
      outcome: "SUCCESS" | "SUCCESS_WITH_COST" | "FAIL_FORWARD";
      publicStateChanges: Array<Record<string, unknown>>;
      mechanicalSummary: string;
    }>
  | StoryEventEnvelope<"private.action_result", {
      playerId: PlayerId;
      actionId: string;
      privateSummary: string;
      privateChangedIds: string[];
    }>
  | StoryEventEnvelope<"prose.ready", { sceneId: string; text: string; fallbackUsed: boolean; contentId: string }>
  | StoryEventEnvelope<"choice.requested", { sceneId: string; choices: Array<{ id: string; label: string; description: string }>; deadlineAt: string }>
  | StoryEventEnvelope<"vote.received", { submittedCount: number }>
  | StoryEventEnvelope<"private.vote_receipt", { playerId: PlayerId; sceneId: string; choiceId: string }>
  | StoryEventEnvelope<"choice.resolved", { sceneId: string; choiceId: string; voteByPlayer?: Record<PlayerId, string> }>
  | StoryEventEnvelope<"safety.paused", { replacementPending: boolean }>
  | StoryEventEnvelope<"scene.replaced_for_safety", { sceneId: string; contentId: string }>
  | StoryEventEnvelope<"chapter.completed", { chapterId: string; publicSummary: string }>
  | StoryEventEnvelope<"story.paused", { snapshotRevision: number }>
  | StoryEventEnvelope<"story.resumed", { snapshotRevision: number }>
  | StoryEventEnvelope<"ending.committed", { endingVector: EndingVector; deterministicSummary: string }>
  | StoryEventEnvelope<"ending.ready", { sceneText: string; epilogues: Array<{ characterId: string; text: string }>; fallbackUsed: boolean }>
  | StoryEventEnvelope<"story.completed", { endingVector: EndingVector }>
  | StoryEventEnvelope<"resync.required", { currentSequence: number; currentRevision: number }>
  | StoryEventEnvelope<"error", { code: string; message: string }>;

export type ClientStorySocketMessage =
  | { type: "hello"; lastSeenSequence: number; lastSeenRevision: number }
  | { type: "ack"; lastSeenSequence: number }
  | { type: "ping"; sentAt: string };

/**
 * Endpoint map
 *
 * POST   /api/stories                              create lobby + invite
 * POST   /api/stories/join                         join by expiring code
 * POST   /api/stories/:id/theme                    host proposes theme; safety envelope is collective
 * POST   /api/stories/:id/characters/me            create/update own character from templates
 * POST   /api/stories/:id/ready                    ready/unready
 * POST   /api/stories/:id/start                    exactly 3 ready players
 * GET    /api/stories/:id                          public participant view
 * GET    /api/stories/:id/private/me               authenticated self-private view
 * POST   /api/stories/:id/scenes/start             internal story engine only
 * POST   /api/stories/:id/actions/interpret        no mutation; candidate + confirmation
 * POST   /api/stories/:id/actions                  idempotent confirmed action
 * POST   /api/stories/:id/choices/vote             sealed joint/private choice
 * POST   /api/stories/:id/safety/pause             any player; identity not broadcast
 * POST   /api/stories/:id/chapters/advance         internal engine after invariants
 * POST   /api/stories/:id/pause                    explicit save checkpoint
 * POST   /api/stories/:id/resume                   resume latest committed revision
 * POST   /api/stories/:id/ending/generate          internal engine after ending vector
 * GET    /api/stories/:id/events?after=N           authorized catch-up/poll fallback
 * POST   /api/stories/:id/ws-ticket                60-second single-use ticket
 * GET    /ws/stories/:id?ticket=...                personalized event stream
 */

export const STORY_REALTIME_POLICY = {
  websocketTicketTtlSeconds: 60,
  heartbeatSeconds: 20,
  staleConnectionSeconds: 60,
  disconnectedSpotlightGraceSeconds: 90,
  voteSeconds: 45,
  eventReplayLimit: 500,
  pollingFallbackSeconds: 3,
} as const;

export type { SubmitStoryActionRequest };
