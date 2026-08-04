/** AI Escape Room authoritative state and graph contracts. */

export type SessionId = string;
export type PlayerId = string;
export type RoomId = string;
export type ObjectId = string;
export type ItemId = string;
export type PuzzleId = string;
export type PuzzleNodeId = string;
export type AttemptId = string;
export type HintId = string;
export type ClueId = string;

export type SessionStatus = "LOBBY" | "ACTIVE" | "PAUSED" | "OVERTIME" | "COMPLETED" | "CANCELLED";
export type PuzzleStatus = "LOCKED" | "AVAILABLE" | "IN_PROGRESS" | "SOLVED" | "ASSISTED_SOLVE";
export type Visibility = "PUBLIC" | `PLAYER:${string}` | "ENGINE_ONLY";
export type NodeKind = "ENTRY" | "PARALLEL" | "GATE" | "META" | "FINAL" | "OPTIONAL";
export type HintTier = "DIRECTION" | "STRONGER_CLUE" | "NEAR_SOLUTION" | "FINAL_ASSIST";

export interface Player {
  id: PlayerId;
  userId: number;
  displayName: string;
  seat: 0 | 1 | 2;
  role: "ENGINEER" | "ANALYST" | "NAVIGATOR";
  ready: boolean;
  connected: boolean;
  abilityCharges: number;
  privateClueIds: ClueId[];
  lastActivityAt?: string;
}

export interface Room {
  id: RoomId;
  key: string;
  displayName: string;
  description: string;
  connectedRoomIds: RoomId[];
  objectIds: ObjectId[];
  discovered: boolean;
  accessible: boolean;
  publicState: Record<string, string | number | boolean | string[]>;
}

export interface EscapeRoomObject {
  id: ObjectId;
  roomId: RoomId;
  definitionKey: string;
  displayName: string;
  description: string;
  state: "HIDDEN" | "VISIBLE" | "LOCKED" | "UNLOCKED" | "OPEN" | "DISABLED";
  visibility: Visibility;
  inspectable: boolean;
  usableItemDefinitionKeys: string[];
  linkedPuzzleNodeIds: PuzzleNodeId[];
  tags: string[];
}

/** Requested domain name without relying on JavaScript's global Object shape. */
export type Object = EscapeRoomObject;

export interface Item {
  id: ItemId;
  definitionKey: string;
  displayName: string;
  description: string;
  state: "AVAILABLE" | "RESERVED" | "COMBINED" | "CONSUMED" | "BROKEN";
  quantity: number;
  durability?: number;
  combinableWith: string[];
  visibility: Visibility;
  sourcePuzzleNodeId?: PuzzleNodeId;
  tags: string[];
}

export interface Inventory {
  id: string;
  holderType: "SHARED" | "PLAYER";
  holderPlayerId?: PlayerId;
  itemIds: ItemId[];
  capacity: number;
}

export type AnswerSpec =
  | { type: "EXACT_CODE"; expectedCiphertext: string; length: number; alphabet: string }
  | { type: "NORMALIZED_TEXT"; expectedHash: string; locale: string; allowedAliasHashes: string[] }
  | { type: "ORDERED_SEQUENCE"; expectedElementHashes: string[] }
  | { type: "SET_EQUALITY"; expectedElementHashes: string[] }
  | { type: "NUMERIC_TOLERANCE"; expectedCiphertext: string; absoluteTolerance: number; relativeTolerance: number; unit?: string }
  | { type: "ITEM_COMBINATION"; requiredDefinitionCounts: Record<string, number>; outputDefinitionKey: string }
  | { type: "STATE_CONDITION"; predicateAstCiphertext: string }
  | { type: "MULTI_STEP"; machineDefinitionCiphertext: string; initialState: string; acceptingStates: string[] };

export interface Puzzle {
  id: PuzzleId;
  templateId: string;
  templateVersion: string;
  title: string;
  description: string;
  difficulty: 1 | 2 | 3 | 4 | 5;
  answerSpec: AnswerSpec;
  status: PuzzleStatus;
  attemptPolicy: {
    maxAttemptsPerThirtySeconds: number;
    feedbackMode: "BINARY" | "TEMPLATE_BOUNDED";
  };
  hintIds: HintId[];
  objectIds: ObjectId[];
  assignedPlayerIds: PlayerId[];
}

export interface DependencyRule {
  mode: "ALL_OF" | "ANY_OF" | "COUNT";
  nodeIds: PuzzleNodeId[];
  requiredCount?: number;
}

export interface PuzzleNode {
  id: PuzzleNodeId;
  kind: NodeKind;
  puzzleId: PuzzleId;
  dependencies: DependencyRule[];
  hintDependencyNodeIds: PuzzleNodeId[];
  grantsItemDefinitionKeys: string[];
  unlocksObjectIds: ObjectId[];
  required: boolean;
  status: PuzzleStatus;
  takeoverPolicy: "NONE" | "AFTER_DISCONNECT_GRACE";
}

export interface PuzzleGraph {
  id: string;
  version: string;
  entryNodeIds: PuzzleNodeId[];
  finalNodeId: PuzzleNodeId;
  nodes: Record<PuzzleNodeId, PuzzleNode>;
  topologicalOrder: PuzzleNodeId[];
  graphHash: string;
}

export interface Attempt {
  id: AttemptId;
  sessionId: SessionId;
  puzzleId: PuzzleId;
  playerId: PlayerId;
  answerType: AnswerSpec["type"];
  answerPayloadHash: string;
  result: "CORRECT" | "INCORRECT" | "DUPLICATE" | "INVALID_FORMAT" | "RATE_LIMITED";
  boundedFeedbackCode?: string;
  stateRevision: number;
  submittedAt: string;
}

export interface Hint {
  id: HintId;
  puzzleId: PuzzleId;
  tier: HintTier;
  canonicalHintCode: string;
  allowedFactIds: string[];
  visibility: Visibility;
  penaltySeconds: number;
  revealed: boolean;
  requestedAt?: string;
}

export interface PrivateClue {
  id: ClueId;
  ownerPlayerId: PlayerId;
  puzzleNodeId: PuzzleNodeId;
  canonicalPayload: Record<string, string | number | boolean | string[]>;
  renderedText: string;
  revealedToOthers: boolean;
  source: "TEMPLATE" | "EMERGENCY_TAKEOVER";
}

export interface ProgressState {
  solvedNodeIds: PuzzleNodeId[];
  availableNodeIds: PuzzleNodeId[];
  blockedNodeIds: PuzzleNodeId[];
  optionalSolvedCount: number;
  requiredSolvedCount: number;
  requiredTotalCount: number;
  currentHintTierByPuzzle: Record<PuzzleId, HintTier | null>;
  overtime: boolean;
  finalAvailable: boolean;
}

export interface TimerState {
  mode: "RELAXED" | "STANDARD_45" | "CHALLENGE_30";
  status: "NOT_STARTED" | "RUNNING" | "PAUSED" | "OVERTIME" | "STOPPED";
  startedAt?: string;
  pausedAt?: string;
  accumulatedPauseSeconds: number;
  remainingSeconds?: number;
}

export interface EscapeRoomSession {
  id: SessionId;
  roomCodeId: string;
  rulesVersion: "nadir-three-v1";
  contentVersion: string;
  status: SessionStatus;
  revision: number;
  players: Player[];
  rooms: Room[];
  objects: EscapeRoomObject[];
  items: Item[];
  inventories: Inventory[];
  puzzles: Puzzle[];
  graph: PuzzleGraph;
  attempts: Attempt[];
  hints: Hint[];
  privateClues: PrivateClue[];
  progress: ProgressState;
  timer: TimerState;
  seedCommitment: string;
  rngCounter: number;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
}

export interface EscapeRoomEngineState extends EscapeRoomSession {
  engineSecrets: {
    rngSeedCiphertext: string;
    solutionPayloadsByPuzzleId: Record<PuzzleId, string>;
    pendingSimultaneousInputs: Record<string, Record<PlayerId, string>>;
    capabilityIds: string[];
  };
}

export interface PublicObjectView {
  id: ObjectId;
  roomId: RoomId;
  displayName: string;
  description: string;
  state: "VISIBLE" | "LOCKED" | "UNLOCKED" | "OPEN" | "DISABLED";
  inspectable: boolean;
}

export interface PublicRoomView {
  id: RoomId;
  displayName: string;
  description: string;
  visibleConnectedRoomIds: RoomId[];
  visibleObjectIds: ObjectId[];
  publicState: Record<string, string | number | boolean | string[]>;
}

export interface PublicItemView {
  id: ItemId;
  displayName: string;
  description: string;
  state: Item["state"];
  quantity: number;
  durability?: number;
}

export interface PublicPuzzleView {
  id: PuzzleId;
  title: string;
  description: string;
  difficulty: 1 | 2 | 3 | 4 | 5;
  status: PuzzleStatus;
  assignedPlayerIds: PlayerId[];
}

export interface PublicEscapeRoomView
  extends Omit<
    EscapeRoomSession,
    | "privateClues"
    | "attempts"
    | "puzzles"
    | "objects"
    | "items"
    | "players"
    | "inventories"
    | "graph"
    | "hints"
    | "progress"
    | "rooms"
  > {
  players: Array<Omit<Player, "privateClueIds">>;
  visibleRooms: PublicRoomView[];
  visibleObjects: PublicObjectView[];
  visibleItems: PublicItemView[];
  sharedInventory: Inventory;
  publicPuzzles: PublicPuzzleView[];
  recentAttempts: Array<Omit<Attempt, "answerPayloadHash">>;
  publicProgress: Omit<ProgressState, "blockedNodeIds">;
  legalActionIds: string[];
}

export interface PrivatePlayerView {
  sessionId: SessionId;
  playerId: PlayerId;
  revision: number;
  publicView: PublicEscapeRoomView;
  privateClues: PrivateClue[];
  privateObjects: EscapeRoomObject[];
  privateInventory: Inventory;
  legalActions: Array<{
    id: string;
    kind: string;
    parametersSchema: Record<string, unknown>;
    actionToken: string;
    expectedRevision: number;
  }>;
}
