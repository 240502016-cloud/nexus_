/**
 * Shared Story authoritative contracts.
 * StoryState is server-only. Clients and model contexts receive audience-specific
 * projections assembled from explicit visibility/knowledge allowlists.
 */

export type StoryId = string;
export type PlayerId = string;
export type CharacterId = string;
export type ChapterId = string;
export type SceneId = string;
export type FactId = string;
export type GoalId = string;
export type MysteryId = string;
export type SecretId = string;
export type PromiseId = string;
export type LocationId = string;
export type ItemId = string;
export type RelationshipId = string;

export type StoryStatus = "LOBBY" | "CHARACTER_SETUP" | "ACTIVE" | "ENDING" | "COMPLETED" | "PAUSED" | "CANCELLED";
export type SceneStatus = "PLANNED" | "ACTIVE" | "RESOLVING" | "COMPLETED" | "REPLACED_FOR_SAFETY";
export type SceneKind = "OPENING" | "SPOTLIGHT" | "JOINT_DECISION" | "INTERLUDE" | "FINALE" | "EPILOGUE";
export type Visibility = "PUBLIC" | "DIRECTOR_INTERNAL" | `PLAYER:${string}` | `CHARACTER:${string}`;
export type FactStatus = "TRUE" | "FALSE" | "UNKNOWN" | "DISPUTED" | "RETIRED";
export type GoalStatus = "ACTIVE" | "COMPLETED" | "FAILED_FORWARD" | "ABANDONED";
export type PromiseStatus = "OPEN" | "FULFILLED" | "SUBVERTED" | "EXPIRED_WITH_CALLBACK";

export interface WorldFact {
  id: FactId;
  key: string;
  value: string | number | boolean | string[];
  status: FactStatus;
  visibility: Visibility;
  sourceSceneId: SceneId;
  establishedRevision: number;
  immutable: boolean;
  tags: string[];
}

export interface CharacterFact {
  id: FactId;
  characterId: CharacterId;
  key: string;
  value: string | number | boolean | string[];
  visibility: Visibility;
  sourceSceneId: SceneId;
  tags: string[];
}

export interface InventoryItem {
  id: ItemId;
  definitionKey: string;
  ownerCharacterId?: CharacterId;
  locationId?: LocationId;
  displayName: string;
  quantity: number;
  durability?: number;
  tags: string[];
  visibility: Visibility;
  acquiredInSceneId: SceneId;
}

export interface RelationshipState {
  id: RelationshipId;
  fromCharacterId: CharacterId;
  toCharacterId: CharacterId;
  trust: number;
  affection: number;
  tension: number;
  obligations: string[];
  publicSummary: string;
  lastChangedSceneId: SceneId;
}

export interface StoryLocation {
  id: LocationId;
  key: string;
  displayName: string;
  description: string;
  connectedLocationIds: LocationId[];
  discovered: boolean;
  accessible: boolean;
  tags: string[];
}

export interface StoryGoal {
  id: GoalId;
  key: string;
  title: string;
  description: string;
  ownerType: "PARTY" | "CHARACTER";
  ownerCharacterId?: CharacterId;
  visibility: Visibility;
  status: GoalStatus;
  progress: number;
  target: number;
  successEffectIds: string[];
  failForwardEffectIds: string[];
  createdInSceneId: SceneId;
  resolvedInSceneId?: SceneId;
}

export interface Mystery {
  id: MysteryId;
  key: string;
  question: string;
  status: "OPEN" | "PARTIALLY_RESOLVED" | "RESOLVED" | "LEFT_AMBIGUOUS";
  progress: number;
  target: number;
  knownClueFactIds: FactId[];
  solutionFactIds: FactId[];
  visibility: Visibility;
  payoffChapter: number;
}

export interface Secret {
  id: SecretId;
  ownerPlayerId?: PlayerId;
  ownerCharacterId?: CharacterId;
  title: string;
  canonicalPayload: Record<string, unknown>;
  revealed: boolean;
  revealConditions: string[];
  permittedAudience: Visibility[];
  createdInChapterId: ChapterId;
  revealedInSceneId?: SceneId;
}

export interface NarrativePromise {
  id: PromiseId;
  setup: string;
  expectedPayoffType: "MYSTERY" | "RELATIONSHIP" | "ITEM" | "THREAT" | "CHARACTER_ARC";
  status: PromiseStatus;
  priority: 1 | 2 | 3;
  establishedInSceneId: SceneId;
  dueByChapter: number;
  payoffSceneId?: SceneId;
  visibility: Visibility;
}

export interface ToneProfile {
  genre: "FANTASY" | "SCI_FI" | "MYSTERY" | "SURVIVAL" | "TIME_LOOP";
  adjectives: [string, string, string];
  pacing: "CONTEMPLATIVE" | "BALANCED" | "FAST";
  humor: "NONE" | "LIGHT" | "FREQUENT";
  horrorIntensity: 0 | 1 | 2 | 3;
  violenceIntensity: 0 | 1 | 2 | 3;
  romance: "OFF" | "SOFT" | "FADE_TO_BLACK";
  playerConflict: "COOPERATIVE" | "CONTROLLED" | "HIGH_WITH_CONSENT";
  betrayal: "OFF" | "NPC_ONLY" | "PLAYER_OPT_IN";
  personalJokes: "OFF" | "GENTLE_OPT_IN";
  darkHumor: "OFF" | "LIGHT" | "FULL_OPT_IN";
  hardLines: string[];
  veils: string[];
}

export interface PlayerChoice {
  id: string;
  sceneId: SceneId;
  playerId: PlayerId;
  choiceDefinitionId: string;
  actionId?: string;
  submittedAt: string;
  revealedAt?: string;
}

export interface Character {
  id: CharacterId;
  playerId: PlayerId;
  name: string;
  archetypeKey: string;
  pronouns: string;
  currentLocationId: LocationId;
  condition: "READY" | "STRAINED" | "INJURED" | "EXHAUSTED";
  spotlightTokens: number;
  assistTokens: number;
  facts: CharacterFact[];
  summary: string;
}

export interface StoryPlayer {
  id: PlayerId;
  userId: number;
  displayName: string;
  seat: 0 | 1 | 2;
  ready: boolean;
  connected: boolean;
  characterId?: CharacterId;
  lastSeenAt?: string;
}

export interface ChapterProgress {
  chapterNumber: number;
  plannedSpotlightPlayerIds: [PlayerId, PlayerId, PlayerId];
  completedSpotlightPlayerIds: PlayerId[];
  jointDecisionCompleted: boolean;
  requiredGoalIds: GoalId[];
  completionReady: boolean;
  sceneCount: number;
}

export interface StoryChapter {
  id: ChapterId;
  number: number;
  title: string;
  objective: string;
  status: "PLANNED" | "ACTIVE" | "COMPLETED";
  progress: ChapterProgress;
  openingStateRevision: number;
  closingStateRevision?: number;
  summaryId?: string;
}

export interface StoryScene {
  id: SceneId;
  chapterId: ChapterId;
  sequence: number;
  kind: SceneKind;
  status: SceneStatus;
  locationId: LocationId;
  spotlightPlayerId?: PlayerId;
  participatingCharacterIds: CharacterId[];
  objective: string;
  proseContentId?: string;
  availableActionIds: string[];
  choices: PlayerChoice[];
  stateBeforeRevision: number;
  stateAfterRevision?: number;
  startedAt?: string;
  deadlineAt?: string;
  completedAt?: string;
}

export interface StorySession {
  id: StoryId;
  roomId: string;
  rulesVersion: "three-paths-v1";
  contentVersion: string;
  status: StoryStatus;
  revision: number;
  /** Lobby may contain fewer; ACTIVE sessions require exactly three. */
  players: StoryPlayer[];
  /** Character setup may be incomplete; ACTIVE sessions require one per player. */
  characters: Character[];
  tone: ToneProfile;
  worldFacts: WorldFact[];
  locations: StoryLocation[];
  activeGoals: StoryGoal[];
  completedGoals: StoryGoal[];
  mysteries: Mystery[];
  secrets: Secret[];
  narrativePromises: NarrativePromise[];
  inventory: InventoryItem[];
  relationships: RelationshipState[];
  chapters: StoryChapter[];
  currentChapterId?: ChapterId;
  currentSceneId?: SceneId;
  playerChoices: PlayerChoice[];
  seedCommitment: string;
  rngCounter: number;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
}

/** Backend-only authoritative state. */
export interface StoryState extends StorySession {
  engineSecrets: {
    rngSeedCiphertext: string;
    secretContentById: Record<SecretId, Secret>;
    endingVector?: EndingVector;
    pendingActionCapabilities: string[];
  };
}

export interface PublicCharacterView extends Omit<Character, "facts"> {
  publicFacts: CharacterFact[];
}

export interface PublicStoryView
  extends Omit<
    StorySession,
    | "secrets"
    | "worldFacts"
    | "activeGoals"
    | "completedGoals"
    | "narrativePromises"
    | "characters"
    | "inventory"
    | "mysteries"
    | "relationships"
    | "playerChoices"
  > {
  characters: PublicCharacterView[];
  worldFacts: WorldFact[];
  activeGoals: StoryGoal[];
  completedGoals: StoryGoal[];
  inventory: InventoryItem[];
  mysteries: Mystery[];
  relationships: RelationshipState[];
  narrativePromises: NarrativePromise[];
  playerChoices: PlayerChoice[];
  currentScene?: StoryScene;
  legalActions: StoryAction[];
}

export interface PrivateStoryView {
  storyId: StoryId;
  playerId: PlayerId;
  revision: number;
  ownCharacter: Character;
  knownSecrets: Secret[];
  privateFacts: Array<WorldFact | CharacterFact>;
  privateGoals: StoryGoal[];
  ownPendingChoice?: PlayerChoice;
  legalActions: StoryAction[];
}

export type StoryActionKind =
  | "INVESTIGATE"
  | "MOVE"
  | "TALK"
  | "USE_ITEM"
  | "ASSIST_PLAYER"
  | "DECEIVE"
  | "REVEAL_SECRET"
  | "REST"
  | "VOTE"
  | "ATTEMPT_RISKY_ACTION";

export interface StoryAction {
  id: string;
  kind: StoryActionKind;
  actorCharacterId: CharacterId;
  label: string;
  parameterSchema: Record<string, unknown>;
  preconditionIds: string[];
  effectEnvelopeId: string;
  expectedRevision: number;
  expiresAt: string;
  actionToken: string;
}

export interface EndingVector {
  primaryGoalOutcome: "RESOLVED" | "FAILED_FORWARD" | "UNRESOLVED";
  threatBand: "LOW" | "MEDIUM" | "HIGH";
  relationshipBand: "UNITED" | "COMPLICATED" | "FRACTURED";
  mysteryBand: "SOLVED" | "PARTIAL" | "AMBIGUOUS";
  promisePayoffRatio: number;
  characterArcOutcomes: Record<CharacterId, "FULFILLED" | "CHANGED" | "OPEN">;
  endingTemplateKey: string;
}
