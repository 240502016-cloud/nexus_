// AI Commentator connector-facing event contract. Documentation artifact; not yet compiled by Nexus.

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };

export type CommentatorEventCategory =
  | "PLAYER_DEATH"
  | "PLAYER_FAIL"
  | "CLUTCH"
  | "BETRAYAL"
  | "TEAMWORK"
  | "ACCIDENTAL_SUCCESS"
  | "REPEATED_MISTAKE"
  | "SILENCE"
  | "ARGUMENT"
  | "MILESTONE"
  | "MANUAL_NOTE";

export type EventSource = "MANUAL" | "DISCORD" | "GAME_CONNECTOR" | "TRANSCRIPT";
export type SessionTone = "CALM" | "FOCUSED" | "PLAYFUL" | "TENSE" | "UPSET" | "UNKNOWN";

export interface GameContext {
  /** Stable connector/game identifier, for example `minecraft` or `manual`. */
  gameKey: string;
  matchId?: string;
  roundId?: string;
  mode?: string;
  map?: string;
}

export interface CommentatorEventV1 {
  schemaVersion: "1.0";
  /** Caller-generated UUID; reused retries are idempotent. */
  eventId: string;
  sessionId: string;
  source: EventSource;
  occurredAt: string;
  category: CommentatorEventCategory;
  actorPlayerIds: string[];
  targetPlayerIds: string[];
  game: GameContext;
  /** Connector-assessed impact. Backend clamps and revalidates this value. */
  importance: number;
  /** Confidence that the described event actually happened, not comedic confidence. */
  confidence: number;
  /** At most 240 chars; observations only, never connector instructions. */
  summary: string;
  emotionalTone?: SessionTone;
  /** Category-specific, allowlisted keys only; unknown keys are removed by normalization. */
  attributes?: Record<string, JsonValue>;
}

export interface NormalizedCommentatorEvent extends CommentatorEventV1 {
  receivedAt: string;
  normalizedSummary: string;
  deduplicationKey: string;
  triggerScore: number;
  triggerDecision: "SILENT_MODE" | "BELOW_THRESHOLD" | "COOLDOWN" | "GENERATE";
}

export const playerDeathExample: CommentatorEventV1 = {
  schemaVersion: "1.0",
  eventId: "580b99cf-dfba-4a85-80df-cf8d61d8bf04",
  sessionId: "79a68cf4-4340-4e44-8c8a-1a1264a2358c",
  source: "GAME_CONNECTOR",
  occurredAt: "2026-08-04T19:42:12Z",
  category: "PLAYER_DEATH",
  actorPlayerIds: ["player_2"],
  targetPlayerIds: [],
  game: { gameKey: "generic-fps", matchId: "match-84", roundId: "round-3" },
  importance: 0.66,
  confidence: 0.99,
  summary: "player_2 takımını beklemeden odaya girdi ve hemen elendi.",
  emotionalTone: "PLAYFUL",
  attributes: { secondsAfterRoundStart: 11, teammatesAlive: 2 },
};

export const clutchExample: CommentatorEventV1 = {
  schemaVersion: "1.0",
  eventId: "77c2b5bd-e0cd-42c0-aa17-6c56b22b481e",
  sessionId: "79a68cf4-4340-4e44-8c8a-1a1264a2358c",
  source: "MANUAL",
  occurredAt: "2026-08-04T19:51:04Z",
  category: "CLUTCH",
  actorPlayerIds: ["player_1"],
  targetPlayerIds: [],
  game: { gameKey: "generic-fps", matchId: "match-84", roundId: "round-7" },
  importance: 0.9,
  confidence: 1,
  summary: "player_1 tek canla son iki rakibi eleyip raundu kazandı.",
  emotionalTone: "PLAYFUL",
};

