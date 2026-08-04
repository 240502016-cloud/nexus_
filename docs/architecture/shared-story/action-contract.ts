import type { CharacterId, FactId, GoalId, ItemId, LocationId, PromiseId, RelationshipId, SceneId, SecretId, StoryActionKind } from "./state-contract";

export type ProposedStateChange =
  | { operation: "ADD_FACT"; candidateKey: string; value: string | number | boolean | string[]; visibility: string; tags: string[] }
  | { operation: "UPDATE_FACT_STATUS"; factId: FactId; status: "TRUE" | "FALSE" | "DISPUTED" | "RETIRED" }
  | { operation: "MOVE_CHARACTER"; characterId: CharacterId; fromLocationId: LocationId; toLocationId: LocationId }
  | { operation: "ADD_ITEM"; definitionKey: string; ownerCharacterId: CharacterId; quantity: number }
  | { operation: "REMOVE_ITEM"; itemId: ItemId; quantity: number }
  | { operation: "ADJUST_RELATIONSHIP"; relationshipId: RelationshipId; axis: "TRUST" | "AFFECTION" | "TENSION"; delta: -2 | -1 | 1 | 2 }
  | { operation: "ADD_GOAL"; candidateKey: string; ownerType: "PARTY" | "CHARACTER"; ownerCharacterId?: CharacterId; target: number }
  | { operation: "COMPLETE_GOAL"; goalId: GoalId }
  | { operation: "ADVANCE_MYSTERY"; mysteryId: string; amount: 1 | 2 }
  | { operation: "ADD_PROMISE"; setup: string; payoffType: string; dueByChapter: number; priority: 1 | 2 | 3 }
  | { operation: "RESOLVE_PROMISE"; promiseId: PromiseId; resolution: "FULFILLED" | "SUBVERTED" | "EXPIRED_WITH_CALLBACK" }
  | { operation: "REVEAL_SECRET"; secretId: SecretId; audience: string[] };

export interface InterpretedActionCandidate {
  actionId: string;
  actionKind: StoryActionKind;
  parameters: Record<string, string | number | boolean | string[]>;
  confidence: number;
  assumptions: string[];
}

export interface ActionInterpretation {
  status: "MATCHED" | "AMBIGUOUS" | "NO_MATCH" | "UNSAFE";
  candidates: InterpretedActionCandidate[];
  requiresPlayerConfirmation: true;
  explanation: string;
}

export interface SubmitStoryActionRequest {
  storyId: string;
  sceneId: SceneId;
  playerId: string;
  actionId: string;
  parameters: Record<string, string | number | boolean | string[]>;
  actionToken: string;
  expectedRevision: number;
}

export interface ResolvedStoryAction {
  actionId: string;
  sceneId: SceneId;
  outcome: "SUCCESS" | "SUCCESS_WITH_COST" | "FAIL_FORWARD";
  committedStateChanges: ProposedStateChange[];
  rejectedProposals: Array<{ proposal: ProposedStateChange; reason: string }>;
  randomProof?: { counter: number; purpose: string; result: number };
  newRevision: number;
  publicEventIds: string[];
  privateEventIds: string[];
}

/**
 * Validation order:
 * 1. authenticated player/character ownership and scene spotlight/assist permission;
 * 2. expected revision, action capability, action kind and action-specific JSON schema;
 * 3. referenced IDs exist and are visible/known to the actor;
 * 4. preconditions, adjacency, item quantity, secret reveal audience and safety policy;
 * 5. effect operation allowlist, per-operation bounds and chapter content budget;
 * 6. continuity invariants and narrative-promise limits;
 * 7. pure deterministic reducer commit. LLM text is generated only afterward.
 */
