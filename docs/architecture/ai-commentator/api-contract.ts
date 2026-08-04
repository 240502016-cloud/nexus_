import type {
  CommentatorEventV1,
  CommentatorEventCategory,
  SessionTone,
} from "./event-contract";

export type CommentaryIntensity = "LOW" | "NORMAL" | "HIGH";
export type SessionStatus = "ACTIVE" | "ENDING" | "ENDED";
export type CommentaryTone = "PLAYFUL" | "DRY" | "HYPE" | "ANALYTICAL" | "GENTLE" | "DRAMATIC";
export type FeedbackType = "FUNNY" | "NOT_FUNNY" | "TOO_HARSH" | "REPETITIVE" | "WRONG_CONTEXT";

export interface CreateCommentarySessionRequest {
  serverId: number;
  gameKey: string;
  playerIds: number[];
  commentatorProfileId: string;
  intensity: CommentaryIntensity;
  textToSpeechEnabled?: boolean;
  outputChannelId?: number;
}

export interface CommentarySession {
  id: string;
  serverId: number;
  gameKey: string;
  playerIds: number[];
  commentatorProfileId: string;
  intensity: CommentaryIntensity;
  silentMode: boolean;
  textToSpeechEnabled: boolean;
  currentTone: SessionTone;
  status: SessionStatus;
  startedAt: string;
  endedAt?: string;
}

export interface JoinSessionRequest {
  playerId: number;
}

export interface PostEventResponse {
  eventId: string;
  accepted: true;
  state: "PENDING" | "DEDUPLICATED" | "FILTERED";
}

export interface GenerateCommentaryRequest {
  /** Normally omitted; internal worker chooses the pending event window. */
  eventId?: string;
  force?: boolean;
}

export interface CommentaryDecision {
  shouldComment: boolean;
  commentary: string | null;
  targetPlayerId: string | null;
  tone: CommentaryTone | null;
  loreReferences: number[];
  confidence: number;
  reasonCode:
    | "NOTABLE_EVENT"
    | "REPEATED_MISTAKE"
    | "LORE_CALLBACK"
    | "MILESTONE"
    | "TEAM_MOMENT"
    | "SAFETY_VETO"
    | "TOO_REPETITIVE"
    | "INSUFFICIENT_CONTEXT";
}

export interface GeneratedCommentary extends CommentaryDecision {
  id: string;
  sessionId: string;
  sourceEventIds: string[];
  profileId: string;
  deliveredAt?: string;
  createdAt: string;
}

export interface SubmitFeedbackRequest {
  playerId: number;
  type: FeedbackType;
  details?: string;
}

export interface EndSessionRequest {
  generateRecap: boolean;
}

export interface SessionHistoryResponse {
  session: CommentarySession;
  events: Array<{
    id: string;
    category: CommentatorEventCategory;
    summary: string;
    occurredAt: string;
    triggerScore: number;
    decision: string;
  }>;
  commentary: GeneratedCommentary[];
  nextCursor?: string;
}

export interface SessionRecap {
  sessionId: string;
  status: "PENDING" | "READY" | "FAILED";
  summary?: string;
  highlightEventIds?: string[];
  commentaryIds?: string[];
}

export interface UpdatePlayerCommentaryPreferencesRequest {
  commentaryEnabled: boolean;
  allowTargetedJokes: boolean;
  allowLoreReferences: boolean;
  maximumHarshness: 0 | 1 | 2 | 3;
  preferredHumorStyles: Array<"DRY" | "ABSURD" | "HYPE" | "ANALYTICAL" | "GENTLE">;
  blockedTopics: string[];
  ttsEnabled: boolean;
}

export interface CommentatorProfile {
  id: string;
  name: string;
  description: string;
  sentenceMaxChars: number;
  harshness: 0 | 1 | 2 | 3;
  loreUsageProbability: number;
  enabledTones: CommentaryTone[];
  isBuiltIn: boolean;
}

export type PostEventRequest = CommentatorEventV1;
