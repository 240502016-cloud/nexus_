/**
 * Three Seals Protocol — authoritative hidden-role state contracts.
 * Never serialize HiddenRoleGameState directly. PublicGameView and
 * PrivatePlayerView are independently constructed allowlist projections.
 */

export type GameId = string;
export type PlayerId = string;
export type RoundId = string;
export type ActionId = string;
export type ClueId = string;
export type VoteId = string;
export type ClaimId = string;

export type GameStatus =
  | "LOBBY"
  | "ROLE_DELIVERY"
  | "ACTIVE"
  | "FINAL_DEDUCTION"
  | "COMPLETED"
  | "CANCELLED";
export type Phase = "CLUE" | "CLAIM" | "DISCUSSION" | "VOTE" | "RESOLUTION" | "DEDUCTION";
export type Office = "SENTINEL" | "ARCHIVIST" | "ENVOY";
export type Mandate = "SEAL" | "REVEAL" | "REDIRECT";
export type Disposition = Mandate;
export type ClueLens = "CONTAINMENT" | "PROVENANCE" | "CONSEQUENCE" | "PUBLIC";
export type Proposition = "SUPPORTS_SAFE" | "EXCLUDES_SAFE" | "RISK_HIGH" | "RISK_LOW";
export type ClaimVerdict = "PENDING" | "SUPPORTED" | "CONTRADICTED" | "UNRESOLVED";
export type GroupOutcome = "STABLE" | "FRACTURED" | "COLLAPSED";

export interface RoleAssignment {
  playerId: PlayerId;
  office: Office;
  mandate: Mandate;
  assignmentCommitment: string;
  revealed: boolean;
}

export interface PrivateObjective {
  id: string;
  playerId: PlayerId;
  templateKey:
    | "SAFE_VOTER"
    | "RELIABLE_WITNESS"
    | "VARIED_BALLOT"
    | "EARLY_COMMITMENT"
    | "STEADY_REPUTATION";
  title: string;
  description: string;
  progress: number;
  target: number;
  scoreReward: 2;
  status: "ACTIVE" | "COMPLETED" | "FAILED";
  revealed: boolean;
}

export interface ClueCanonicalMeaning {
  subjectOptionId: string;
  proposition: Proposition;
  qualifierTags: string[];
}

export interface Clue {
  id: ClueId;
  roundId: RoundId;
  lens: ClueLens;
  ownerPlayerId?: PlayerId;
  visibility: "PUBLIC" | "PRIVATE_PLAYER";
  strength: "DECISIVE" | "CORROBORATING";
  canonicalMeaning: ClueCanonicalMeaning;
  renderedText: string;
  contentVersion: string;
}

export interface CrisisOption {
  id: string;
  disposition: Disposition;
  title: string;
  description: string;
}

export interface Crisis {
  scenarioKey: string;
  title: string;
  publicBrief: string;
  options: [CrisisOption, CrisisOption, CrisisOption];
  /** Authoritative state only; excluded from all active-game views. */
  safeOptionId: string;
}

export interface Claim {
  id: ClaimId;
  gameId: GameId;
  roundId: RoundId;
  playerId: PlayerId;
  kind: "EVIDENCE" | "ACCUSATION";
  subjectOptionId?: string;
  proposition?: Proposition;
  targetPlayerId?: PlayerId;
  guessedOffice?: Office;
  guessedMandate?: Mandate;
  flavorText?: string;
  reputationStake: 0 | 1;
  verdict: ClaimVerdict;
  createdAt: string;
}

export interface Vote {
  id: VoteId;
  gameId: GameId;
  roundId: RoundId;
  playerId: PlayerId;
  optionId: string;
  submittedAt: string;
  revealedAt?: string;
}

export interface PublicAction {
  id: ActionId;
  gameId: GameId;
  roundId: RoundId;
  playerId: PlayerId;
  kind: "CREATE_CLAIM" | "RETRACT_CLAIM" | "REQUEST_RULE" | "PASS";
  payload: Record<string, unknown>;
  revision: number;
  createdAt: string;
}

export interface PrivateAction {
  id: ActionId;
  gameId: GameId;
  roundId: RoundId;
  playerId: PlayerId;
  kind: "INSPECT" | "CAST_VOTE" | "FINAL_DEDUCTION";
  payload: Record<string, unknown>;
  revision: number;
  createdAt: string;
}

export interface HiddenRolePlayer {
  id: PlayerId;
  userId: number;
  displayName: string;
  seat: 0 | 1 | 2;
  ready: boolean;
  connected: boolean;
  reputation: number;
  publicInsight: number;
  secretMandatePoints: number;
  supportedClaims: number;
  contradictedClaims: number;
  safeVotes: number;
  accusationStakeLocked: 0 | 1;
  role: RoleAssignment;
  objective: PrivateObjective;
}

export interface RoundResult {
  roundId: RoundId;
  roundNumber: 1 | 2 | 3 | 4;
  selectedOptionId: string;
  selectedDisposition: Disposition;
  safeOptionId: string;
  wasSafe: boolean;
  stabilityDelta: number;
  voteByPlayer: Record<PlayerId, string>;
  claimVerdicts: Record<ClaimId, ClaimVerdict>;
  publicScoreDeltas: Record<PlayerId, number>;
  resolvedAt: string;
}

export interface HiddenRoleRound {
  id: RoundId;
  number: 1 | 2 | 3 | 4;
  phase: Phase;
  phaseDeadlineAt: string;
  arbiterPlayerId: PlayerId;
  crisis: Crisis;
  clues: Clue[];
  claims: Claim[];
  votes: Vote[];
  result?: RoundResult;
}

export interface HiddenRoleGame {
  id: GameId;
  roomId: string;
  rulesVersion: "three-seals-v1";
  contentVersion: string;
  status: GameStatus;
  revision: number;
  players: [HiddenRolePlayer, HiddenRolePlayer, HiddenRolePlayer];
  currentRound?: HiddenRoleRound;
  completedRounds: RoundResult[];
  stability: number;
  stabilityMaximum: 5;
  seedCommitment: string;
  rngCounter: number;
  groupOutcome?: GroupOutcome;
  winnerPlayerId?: PlayerId;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
}

export interface HiddenRoleGameState extends HiddenRoleGame {
  engineSecrets: {
    rngSeedCiphertext: string;
    scenarioOrder: string[];
    roleAssignments: Record<PlayerId, RoleAssignment>;
    privateObjectives: Record<PlayerId, PrivateObjective>;
    pendingVotes: Record<PlayerId, Vote>;
    finalDeductions: Record<PlayerId, FinalDeduction>;
  };
}

export interface PublicPlayerView {
  id: PlayerId;
  displayName: string;
  seat: 0 | 1 | 2;
  connected: boolean;
  reputation: number;
  publicInsight: number;
  supportedClaims: number;
  contradictedClaims: number;
  safeVotes: number;
}

export interface PublicRoundView {
  id: RoundId;
  number: 1 | 2 | 3 | 4;
  phase: Phase;
  phaseDeadlineAt: string;
  arbiterPlayerId: PlayerId;
  crisis: Omit<Crisis, "safeOptionId">;
  publicClues: Clue[];
  claims: Claim[];
  submittedVoteCount: number;
  revealedVotes?: Vote[];
  result?: RoundResult;
}

export interface PublicGameView {
  id: GameId;
  rulesVersion: "three-seals-v1";
  contentVersion: string;
  status: GameStatus;
  revision: number;
  players: [PublicPlayerView, PublicPlayerView, PublicPlayerView];
  currentRound?: PublicRoundView;
  completedRounds: RoundResult[];
  stability: number;
  stabilityMaximum: 5;
  seedCommitment: string;
  groupOutcome?: GroupOutcome;
  winnerPlayerId?: PlayerId;
}

export interface PrivatePlayerView {
  gameId: GameId;
  playerId: PlayerId;
  revision: number;
  office: Office;
  mandate: Mandate;
  privateObjective: PrivateObjective;
  currentPrivateClue?: Clue;
  ownVote?: Vote;
  mandatePoints: number;
  legalActions: LegalAction[];
}

export interface LegalAction {
  id: string;
  kind: "INSPECT" | "CREATE_CLAIM" | "CAST_VOTE" | "FINAL_DEDUCTION" | "PASS";
  parametersSchema: Record<string, unknown>;
  expectedRevision: number;
  actionToken: string;
}

export interface FinalDeduction {
  playerId: PlayerId;
  officeByPlayer: Record<PlayerId, Office>;
  mandateByPlayer: Record<PlayerId, Mandate>;
  submittedAt: string;
}

export interface HiddenRoleGameResult {
  gameId: GameId;
  groupOutcome: GroupOutcome;
  winnerPlayerId: PlayerId;
  assignments: RoleAssignment[];
  objectives: PrivateObjective[];
  scoreBreakdown: Array<{
    playerId: PlayerId;
    publicInsight: number;
    mandatePoints: number;
    objectivePoints: number;
    deductionPoints: number;
    accusationPoints: number;
    total: number;
    finalReputation: number;
    rank: 1 | 2 | 3;
  }>;
  tieBreakApplied?: "REPUTATION" | "SAFE_VOTES" | "SUPPORTED_CLAIMS" | "FEWER_CONTRADICTIONS" | "COMMITTED_RNG";
  rngSeedReveal: string;
}

export interface SecretLog {
  id: string;
  gameId: GameId;
  sequence: number;
  audiencePlayerId?: PlayerId;
  eventType: string;
  payloadCiphertext: string;
  payloadHash: string;
  createdAt: string;
}
