// Party Lore HTTP contract. This file is documentation and is not compiled by the frontend.

export type LoreCategory =
  | "LEGENDARY_EVENT"
  | "REPEATED_FAILURE"
  | "RECURRING_BEHAVIOR"
  | "NICKNAME_ORIGIN"
  | "QUOTE"
  | "RIVALRY"
  | "ACHIEVEMENT"
  | "BETRAYAL"
  | "RUNNING_JOKE"
  | "GROUP_TRADITION"
  | "FAILED_STRATEGY"
  | "UNEXPECTED_SUCCESS"
  | "PLAYER_PREFERENCE"
  | "HUMOR_BOUNDARY"
  | "SESSION_REFERENCE";

export type Sensitivity = "LOW" | "MEDIUM" | "HIGH" | "PROHIBITED";
export type ConsentState =
  | "AUTO_ALLOWED"
  | "CONFIRM_REQUIRED"
  | "CONFIRMED"
  | "RESTRICTED"
  | "NEVER_REFERENCE"
  | "DELETED";
export type LoreStatus = "ACTIVE" | "DISPUTED" | "ARCHIVED" | "MERGED" | "DELETED";
export type UsageModule =
  | "COMMENTARY"
  | "MEME"
  | "HIGHLIGHT"
  | "ROAST"
  | "BOARD_GAME"
  | "HIDDEN_ROLE"
  | "SHARED_STORY"
  | "ESCAPE_ROOM"
  | "PRIVATE_RECAP";

export interface SubmitRawEventRequest {
  serverId: number;
  sourceType:
    | "MANUAL_NOTE"
    | "COMMENTATOR_EVENT"
    | "MATCH_SUMMARY"
    | "HIGHLIGHT_TRANSCRIPT"
    | "SUBMITTED_MESSAGE"
    | "MEME_METADATA"
    | "SYSTEM_EVENT";
  sourceExternalId?: string;
  intentionallySubmitted: boolean;
  occurredAt?: string;
  content: string;
  metadata?: Record<string, string | number | boolean | null>;
}

export interface RawEventAccepted {
  rawEventId: number;
  processingState: "PENDING";
}

export interface ExtractCandidateResponse {
  rawEventId: number;
  outcome: "CANDIDATE_CREATED" | "NOT_STORED";
  candidate?: LoreCandidate;
  reasonCode: string;
}

export interface LoreCandidate {
  id: number;
  title: string;
  summary: string;
  category: LoreCategory;
  participantIds: number[];
  importance: number;
  humorScore: number;
  sensitivity: Exclude<Sensitivity, "PROHIBITED">;
  confidence: number;
  tags: string[];
  requiresConfirmation: boolean;
  duplicateOfLoreId?: number;
  state: "PENDING" | "AUTO_ACCEPTED" | "CONFIRMED" | "REJECTED" | "EXPIRED";
}

export interface ConfirmCandidateRequest {
  expectedVersion: string;
  edits?: Partial<Pick<LoreCandidate, "title" | "summary" | "category" | "participantIds" | "tags">>;
  consentState?: "CONFIRMED" | "RESTRICTED";
  allowedUsageTypes?: UsageModule[];
}

export interface RejectCandidateRequest {
  reason: "NOT_MEMORABLE" | "INACCURATE" | "DUPLICATE" | "PRIVATE" | "OTHER";
  note?: string;
}

export interface LoreEntry {
  id: number;
  title: string;
  summary: string;
  category: LoreCategory;
  canonicalEventDate?: string;
  participantIds: number[];
  confidence: number;
  importance: number;
  humorScore: number;
  sensitivity: Sensitivity;
  consentState: ConsentState;
  allowedUsageTypes: UsageModule[];
  status: LoreStatus;
  tags: string[];
  usageCount: number;
  lastUsedAt?: string;
  cooldownUntil?: string;
  createdAt: string;
  updatedAt: string;
  version: string;
}

export interface LoreSearchQuery {
  serverId: number;
  q?: string;
  playerIds?: number[];
  categories?: LoreCategory[];
  statuses?: LoreStatus[];
  cursor?: string;
  limit?: number;
}

export interface RetrieveLoreRequest {
  serverId: number;
  module: UsageModule;
  query: string;
  currentParticipantIds: number[];
  eventTypes?: LoreCategory[];
  excludeLoreIds?: number[];
  maxItems?: number;
  tokenBudget?: number;
  requestId: string;
}

export interface RetrievedLoreItem {
  loreId: number;
  summary: string;
  participantIds: number[];
  category: LoreCategory;
  allowedUsageTypes: UsageModule[];
  lastUsedAt?: string;
  confidence: number;
  score: number;
  evidenceCount: number;
}

export interface RetrieveLoreResponse {
  items: RetrievedLoreItem[];
  omittedReason?: "NO_RELEVANT_LORE" | "PRIVACY_FILTERED" | "COOLDOWN" | "TOKEN_BUDGET";
}

export interface EditLoreRequest {
  expectedVersion: string;
  patch: Partial<
    Pick<
      LoreEntry,
      | "title"
      | "summary"
      | "category"
      | "canonicalEventDate"
      | "participantIds"
      | "importance"
      | "humorScore"
      | "sensitivity"
      | "consentState"
      | "allowedUsageTypes"
      | "status"
      | "tags"
    >
  >;
  reason: string;
}

export interface MergeLoreRequest {
  sourceLoreId: number;
  targetLoreId: number;
  expectedSourceVersion: string;
  expectedTargetVersion: string;
  reason: string;
}

export interface DeleteLoreRequest {
  expectedVersion: string;
  reason?: string;
  artifactPolicy: "KEEP_WITHOUT_LORE_LINK" | "REDACT_GENERATED_ARTIFACTS";
}

export interface RecordUsageRequest {
  requestId: string;
  module: UsageModule;
  loreIds: number[];
  artifactId?: string;
  usedForPlayerId?: number;
  renderedPhrases?: string[];
}

export interface AddFeedbackRequest {
  feedbackType:
    | "ACCURATE"
    | "INACCURATE"
    | "FUNNY"
    | "NOT_FUNNY"
    | "OVERUSED"
    | "WRONG_PLAYER"
    | "UNCOMFORTABLE"
    | "REQUEST_DELETE";
  details?: string;
}

export interface PlayerHumorPreferences {
  allowCommentary: boolean;
  allowMemes: boolean;
  allowRoastBattle: boolean;
  allowPrivateRecap: boolean;
  neverUseAgainstPlayer: boolean;
  maximumSensitivity: "LOW" | "MEDIUM" | "HIGH";
  blockedCategories: LoreCategory[];
  blockedTags: string[];
}
