/**
 * AI Board Game authoritative engine contracts.
 *
 * The server owns GameState. Clients receive a viewer-specific GameView only.
 * All random results come from the committed server RNG and every mutation
 * increments `revision` exactly once.
 */

export type GameId = string;
export type PlayerId = string;
export type TileId = string;
export type CardId = string;
export type EventId = string;
export type ActionId = string;
export type TurnId = string;
export type ObjectiveId = string;
export type AllianceId = string;

export type GameStatus =
  | "LOBBY"
  | "OBJECTIVE_SELECTION"
  | "ACTIVE"
  | "COMPLETED"
  | "ABANDONED";

export type GroupOutcome = "PORTAL_OPENED" | "ROUGH_ESCAPE";
export type ResourceType = "ENERGY" | "SCRAP" | "FAME" | "SHIELD" | "MOMENTUM";
export type TileType = "CAMP" | "SALVAGE" | "TRIAL" | "CROSSROADS" | "PORTAL";
export type CardKind = "OPPORTUNITY" | "WORLD" | "PACT" | "TWIST";
export type CardZone = "DECK" | "HAND" | "DISCARD" | "BOARD" | "RESOLVED";
export type StatusKind = "DISTRUSTED" | "EXHAUSTED" | "INSPIRED" | "SHIELDED";
export type ActionKind =
  | "MOVE"
  | "SCAVENGE"
  | "REST"
  | "ATTEMPT_TRIAL"
  | "ASSIST_TRIAL"
  | "CHARGE_PORTAL"
  | "DEPOSIT_SIGIL"
  | "DRAW_OPPORTUNITY"
  | "CONTEST_CROSSROADS"
  | "TRADE"
  | "FORM_PACT"
  | "RESOLVE_PACT"
  | "PLAY_CARD"
  | "END_TURN"
  | "SAFE_TIMEOUT";

export interface Resource {
  type: ResourceType;
  amount: number;
  min: number;
  max: number;
}

export interface StatusEffect {
  id: string;
  kind: StatusKind;
  sourceEventId: EventId;
  stacks: number;
  expiresAtRound: number;
  public: boolean;
}

export interface Player {
  id: PlayerId;
  userId: number;
  displayName: string;
  seat: 0 | 1 | 2;
  connected: boolean;
  ready: boolean;
  tileId: TileId;
  resources: Record<ResourceType, number>;
  sigils: string[];
  depositedSigils: number;
  contributionPoints: number;
  betrayals: number;
  statuses: StatusEffect[];
  /** Hidden from other players until the game ends. */
  objectiveIds: ObjectiveId[];
  /** Hidden hand; other players receive only handCount. */
  handCardIds: CardId[];
}

export interface Tile {
  id: TileId;
  type: TileType;
  region: "EMBER" | "TIDE" | "GROVE" | "CENTER";
  label: string;
  adjacentTileIds: TileId[];
  trialSigilId?: string;
  claimedByPlayerId?: PlayerId;
  exhaustedUntilRound?: number;
}

export interface Board {
  layoutVersion: "last-portal-v1";
  tiles: Record<TileId, Tile>;
  startTileBySeat: Record<0 | 1 | 2, TileId>;
  portalTileId: TileId;
  portalCharge: number;
  depositedSigilIds: string[];
  chaos: number;
  chaosLimit: 12;
}

export interface Turn {
  id: TurnId;
  round: number;
  seatOrder: [0 | 1 | 2, 0 | 1 | 2, 0 | 1 | 2];
  activeSeatIndex: 0 | 1 | 2;
  activePlayerId: PlayerId;
  actionPointsRemaining: number;
  startedAt: string;
  deadlineAt: string;
  endedAt?: string;
}

export interface ResourceCost {
  resource: ResourceType;
  amount: number;
}

export interface LegalActionOption {
  id: string;
  label: string;
  value: string | number | boolean;
}

export interface Action {
  id: ActionId;
  kind: ActionKind;
  gameId: GameId;
  playerId: PlayerId;
  turnId: TurnId;
  actionPointCost: 0 | 1 | 2;
  resourceCosts: ResourceCost[];
  options: LegalActionOption[];
  legalUntilRevision: number;
  actionToken: string;
}

export type EffectTemplateId =
  | "RESOURCE_DELTA"
  | "RISK_REWARD_CHECK"
  | "CHOICE_RESOURCE_OR_FAME"
  | "COOPERATIVE_CHECK"
  | "STATUS_TRADEOFF"
  | "TILE_SHORTCUT"
  | "PACT_MISSION";

export interface EffectSpec {
  templateId: EffectTemplateId;
  /** Schema-validated, bounded parameters; never executable code. */
  parameters: Record<string, string | number | boolean | string[]>;
  balanceBudget: 1 | 2 | 3;
}

export interface Card {
  id: CardId;
  definitionKey: string;
  kind: CardKind;
  title: string;
  description: string;
  effect: EffectSpec;
  zone: CardZone;
  ownerPlayerId?: PlayerId;
  generated: boolean;
  /** Lore changes presentation only; it cannot change effect or balanceBudget. */
  loreReferenceIds: string[];
}

export interface Event {
  id: EventId;
  definitionKey: string;
  title: string;
  description: string;
  effect: EffectSpec;
  choices: Array<{
    id: string;
    label: string;
    effect: EffectSpec;
  }>;
  requiresChoiceFrom: PlayerId[];
  resolutionStatus: "PENDING" | "RESOLVED" | "EXPIRED";
}

export interface Objective {
  id: ObjectiveId;
  templateKey: string;
  ownerPlayerId: PlayerId;
  title: string;
  description: string;
  progress: number;
  target: number;
  fameReward: 3;
  status: "OFFERED" | "SELECTED" | "COMPLETED" | "FAILED" | "DISCARDED";
  revealed: boolean;
}

export interface Alliance {
  id: AllianceId;
  memberPlayerIds: [PlayerId, PlayerId];
  pactCardId: CardId;
  createdAtRound: number;
  expiresAtRound: number;
  status: "OFFERED" | "ACTIVE" | "HONORED" | "BETRAYED" | "EXPIRED";
  betrayedByPlayerId?: PlayerId;
}

export type GameLogAudience = "PUBLIC" | "SYSTEM" | `PLAYER:${string}`;

export interface GameLog {
  id: EventId;
  gameId: GameId;
  sequence: number;
  revision: number;
  type: string;
  actorPlayerId?: PlayerId;
  audience: GameLogAudience;
  /** Structured, allowlisted event data; never raw prompts or hidden state. */
  payload: Record<string, unknown>;
  createdAt: string;
}

export interface CommittedRngState {
  algorithm: "HMAC_SHA256_COUNTER_V1";
  seedCommitment: string;
  counter: number;
  /** Published only in COMPLETED games so the sequence can be verified. */
  revealedSeed?: string;
}

export interface Game {
  id: GameId;
  roomId: string;
  rulesVersion: "last-portal-v1";
  contentVersion: string;
  status: GameStatus;
  revision: number;
  round: number;
  maximumRounds: 8;
  players: [Player, Player, Player];
  board: Board;
  turn?: Turn;
  cards: Record<CardId, Card>;
  events: Record<EventId, Event>;
  objectives: Record<ObjectiveId, Objective>;
  alliances: Alliance[];
  rng: CommittedRngState;
  groupOutcome?: GroupOutcome;
  winnerPlayerId?: PlayerId;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
}

/** Authoritative state: backend/worker only, never serialized directly. */
export interface GameState extends Game {
  engineSecrets: {
    rngSeedCiphertext: string;
    deckOrderByKind: Partial<Record<CardKind, CardId[]>>;
    pendingChoiceSecrets: Record<string, Record<PlayerId, string>>;
  };
}

/** Privacy-safe player projection returned by REST and WebSocket snapshots. */
export interface PlayerView extends Omit<Player, "objectiveIds" | "handCardIds"> {
  handCount: number;
  ownHand?: Card[];
  ownObjectives?: Objective[];
}

export interface GameView
  extends Omit<Game, "players" | "cards" | "objectives" | "events"> {
  viewerPlayerId: PlayerId;
  players: [PlayerView, PlayerView, PlayerView];
  visibleCards: Card[];
  visibleObjectives: Objective[];
  visibleEvents: Event[];
  legalActions: Action[];
}

export interface GameResult {
  gameId: GameId;
  groupOutcome: GroupOutcome;
  winnerPlayerId: PlayerId;
  scores: Array<{
    playerId: PlayerId;
    fameBeforeObjectives: number;
    objectiveFame: number;
    finalFame: number;
    contributionPoints: number;
    completedObjectives: number;
    resourcesRemaining: number;
    betrayals: number;
    rank: 1 | 2 | 3;
  }>;
  tieBreakApplied?:
    | "CONTRIBUTION"
    | "OBJECTIVES"
    | "RESOURCES"
    | "FEWER_BETRAYALS"
    | "COMMITTED_RNG";
  rngSeedReveal: string;
}
