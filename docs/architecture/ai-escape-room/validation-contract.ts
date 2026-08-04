/** Strict deterministic answer validation. No LLM output is accepted as correctness. */

export type SubmissionValue =
  | { type: "EXACT_CODE"; code: string }
  | { type: "NORMALIZED_TEXT"; text: string; locale: string }
  | { type: "ORDERED_SEQUENCE"; elements: string[] }
  | { type: "SET_EQUALITY"; elements: string[] }
  | { type: "NUMERIC_TOLERANCE"; value: number; unit?: string }
  | { type: "ITEM_COMBINATION"; itemInstanceIds: string[] }
  | { type: "STATE_CONDITION"; actionKey: string; parameters: Record<string, string | number | boolean> }
  | { type: "MULTI_STEP"; transitionKey: string; input: string | number | boolean };

export interface ValidationContext {
  sessionId: string;
  puzzleId: string;
  playerId: string;
  expectedRevision: number;
  visibleObjectIds: string[];
  usableItemInstanceIds: string[];
  currentMachineState?: string;
}

export interface ValidationResult {
  validFormat: boolean;
  correct: boolean;
  resultCode:
    | "CORRECT"
    | "INCORRECT"
    | "INVALID_FORMAT"
    | "STALE_REVISION"
    | "PUZZLE_LOCKED"
    | "UNAUTHORIZED_ITEM"
    | "INVALID_TRANSITION"
    | "DUPLICATE";
  normalizedAnswerHash?: string;
  nextMachineState?: string;
  boundedFeedbackCode?: string;
  committedEffectIds: string[];
}

/**
 * NORMALIZED_TEXT pipeline, pinned by rules version:
 * 1. reject control characters and mixed-script confusables;
 * 2. Unicode NFKC;
 * 3. locale-aware case folding (including Turkish I rules when locale is tr-TR);
 * 4. trim and collapse Unicode whitespace;
 * 5. remove only template-allowlisted punctuation;
 * 6. compare an HMAC of normalized text with expected/explicit alias HMACs.
 *
 * It never uses semantic similarity, embeddings, fuzzy distance or an LLM. Aliases
 * are finite and generated before the session. Leading zeroes in EXACT_CODE remain
 * significant and exact codes never pass through text normalization.
 */

export const VALIDATOR_RULES = {
  EXACT_CODE: "constant-time exact equality over fixed alphabet/length",
  NORMALIZED_TEXT: "pinned normalization then expected-or-alias HMAC equality",
  ORDERED_SEQUENCE: "same length and constant-time element-by-element hash equality",
  SET_EQUALITY: "unique normalized element hashes, equal cardinality and set equality",
  NUMERIC_TOLERANCE: "unit-normalize, then abs(error) <= max(absTol, relTol * abs(expected))",
  ITEM_COMBINATION: "transactionally compare definition-key multiset and item states",
  STATE_CONDITION: "evaluate allowlisted predicate AST against authoritative state",
  MULTI_STEP: "apply one transition in a versioned finite-state machine; accept only accepting state",
} as const;

export interface AnswerInterpretation {
  status: "MATCHED" | "AMBIGUOUS" | "NO_MATCH";
  candidateSubmissions: SubmissionValue[];
  confidence: number;
  requiresPlayerConfirmation: true;
  /** Never contains correctness or closeness. */
  explanation: string;
}
