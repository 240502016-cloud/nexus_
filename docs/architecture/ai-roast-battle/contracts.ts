// AI Roast Battle domain and HTTP contracts. Documentation artifact; backend mirrors with Pydantic.

export type RoastIntensity = 0 | 1 | 2 | 3 | 4;

export type RoastMode =
  | "BALANCED_SPOTLIGHT"
  | "TOPIC_CARDS"
  | "PLAYER_WRITTEN_AI_JUDGE"
  | "PLAYER_VS_AI"
  | "TEAM_ROAST"
  | "FAKE_AWARDS"
  | "SESSION_RECAP_GAUNTLET";

export type RoastAngle =
  | "OVERCONFIDENCE"
  | "BAD_NAVIGATION"
  | "PANIC"
  | "BLAMING_LAG"
  | "REPEATED_MISTAKE"
  | "OVERPREPARATION"
  | "FORGOTTEN_MECHANIC"
  | "ACCIDENTAL_SUCCESS"
  | "POOR_TEAMWORK"
  | "DRAMATIC_REACTION"
  | "FAKE_LEADERSHIP"
  | "SILENT_FAILURE"
  | "BAD_TIMING"
  | "RESOURCE_HOARDING"
  | "PREMATURE_CELEBRATION"
  | "GREEDY_LOOT"
  | "FRIENDLY_FIRE"
  | "PLAN_COLLAPSE"
  | "AFK_TIMING"
  | "BUTTON_MASHING";

export type GamingTopic =
  | "GAMING_MISTAKES"
  | "FAILED_STRATEGIES"
  | "HARMLESS_QUOTES"
  | "MATCH_STATISTICS"
  | "FUNNY_HIGHLIGHTS"
  | "CONFIRMED_PARTY_LORE"
  | "SELF_DESCRIPTIONS"
  | "NAVIGATION"
  | "TEAMWORK"
  | "INVENTORY"
  | "TIMING"
  | "REACTIONS";

export type HardBlockedCategory =
  | "MEDICAL"
  | "MENTAL_HEALTH"
  | "APPEARANCE"
  | "PROTECTED_IDENTITY"
  | "FAMILY"
  | "ROMANTIC_OR_SEXUAL_HISTORY"
  | "WORK"
  | "FINANCE"
  | "TRAUMA"
  | "REAL_CONFLICT"
  | "PRIVATE_MESSAGES"
  | "SECRETS"
  | "UNVERIFIED_REAL_LIFE_CLAIMS";

export interface RoastProfile {
  playerId: number;
  roastEnabled: boolean;
  maximumIntensity: RoastIntensity;
  allowedTopics: GamingTopic[];
  blockedTopics: GamingTopic[];
  allowPartyLore: boolean;
  allowRecentFailures: boolean;
  allowQuotes: boolean;
  allowMatchStatistics: boolean;
  allowHighlights: boolean;
  allowSelfDescriptions: boolean;
  allowMildProfanity: boolean;
  /** Product-mandatory values cannot be removed by an update request. */
  hardBlockedCategories: HardBlockedCategory[];
  consentVersion: number;
  updatedAt: string;
}

export interface UpdateRoastProfileRequest {
  roastEnabled: boolean;
  maximumIntensity: RoastIntensity;
  allowedTopics: GamingTopic[];
  blockedTopics: GamingTopic[];
  allowPartyLore: boolean;
  allowRecentFailures: boolean;
  allowQuotes: boolean;
  allowMatchStatistics: boolean;
  allowHighlights: boolean;
  allowSelfDescriptions: boolean;
  allowMildProfanity: boolean;
}

export interface CreateRoastSessionRequest {
  serverId: number;
  playerIds: [number, number, number];
  mode: RoastMode;
  requestedIntensity: RoastIntensity;
  maximumRounds?: number;
}

export interface RoastSession {
  id: string;
  serverId: number;
  playerIds: [number, number, number];
  mode: RoastMode;
  requestedIntensity: RoastIntensity;
  status: "CONSENT_PENDING" | "ACTIVE" | "ENDING" | "ENDED" | "CANCELLED";
  currentRoundNumber: number;
  maximumRounds: number;
  startedAt?: string;
  endedAt?: string;
}

export interface SubmitSessionConsentRequest {
  playerId: number;
  consentVersion: number;
  decision: "READY" | "DECLINE";
}

export interface StartRoundRequest {
  requestedTargetPlayerId?: number;
  submittedTopic?: GamingTopic;
}

export interface RoastRound {
  id: string;
  sessionId: string;
  roundNumber: number;
  targetPlayerId: number | null;
  effectiveIntensity: RoastIntensity;
  status: "PENDING" | "GENERATING" | "VOTING" | "COMPLETED" | "SKIPPED";
}

export interface RoastCandidate {
  id: string;
  roundId: string;
  allowed: boolean;
  targetPlayerId: number | null;
  roastText: string;
  sourceLoreIds: number[];
  angle: RoastAngle | "GROUP_GENERIC" | "AI_SELF_ROAST";
  intensity: RoastIntensity;
  riskFlags: string[];
  repetitionScore: number;
  confidence: number;
  qualityScore: number;
}

export interface GenerateRoastResponse {
  jobId: string;
  status: "QUEUED" | "READY" | "NO_SAFE_MATERIAL" | "FAILED";
  candidate?: RoastCandidate;
  fallbackType?: "GROUP_GENERIC" | "AI_SELF_ROAST" | "SKIP_ROUND";
}

export interface SubmitRoastVoteRequest {
  playerId: number;
  vote: "FUNNY" | "OKAY" | "PASS";
  emoji?: "😂" | "👏" | "😐";
  reactionTimeMs?: number;
}

export interface SubmitRoastFeedbackRequest {
  playerId: number;
  type: "FUNNY" | "TOO_HARSH" | "REPETITIVE" | "WRONG_CONTEXT" | "SKIP_FUTURE";
  details?: string;
}

export interface RegenerateRoastRequest {
  avoidCandidateIds: string[];
  gentler: boolean;
}

export interface EndRoastSessionRequest {
  generateRecap: boolean;
}

export interface RoastRecap {
  sessionId: string;
  status: "PENDING" | "READY" | "FAILED";
  title?: string;
  summary?: string;
  awards?: Array<{ playerId: number | null; award: string }>;
  winningCandidateIds?: string[];
}
