/** Tool schemas and authorization boundaries for AI Escape Room. */

export type JsonSchema = Record<string, unknown>;
type Permission = "PARTICIPANT_PUBLIC" | "AUTHENTICATED_SELF" | "PLAYER_CAPABILITY" | "ENGINE_ONLY";

export interface EscapeToolDefinition {
  name: string;
  permission: Permission;
  mutatesState: boolean;
  hostModelAccess: "READ_ONLY" | "NONE";
  description: string;
  inputSchema: JsonSchema;
}

const id = { type: "string", minLength: 1, maxLength: 128 } as const;
const revision = { type: "integer", minimum: 0 } as const;
const capability = {
  type: "string",
  minLength: 32,
  maxLength: 2048,
  description: "Single-use engine capability bound to session, player, operation, exact argument hash and revision.",
} as const;

export const ESCAPE_ROOM_TOOLS: EscapeToolDefinition[] = [
  {
    name: "get_public_room_state",
    permission: "PARTICIPANT_PUBLIC",
    mutatesState: false,
    hostModelAccess: "READ_ONLY",
    description: "Return the spoiler-safe shared projection: visible rooms/objects/items, public puzzle status, timer and shared observations.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["sessionId"],
      properties: { sessionId: id, minimumRevision: revision },
    },
  },
  {
    name: "get_private_player_view",
    permission: "AUTHENTICATED_SELF",
    mutatesState: false,
    hostModelAccess: "NONE",
    description: "Return only the authenticated player's private clues, objects, inventory and legal actions plus the public view.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["sessionId", "playerId"],
      properties: { sessionId: id, playerId: id, minimumRevision: revision },
    },
  },
  {
    name: "inspect_object",
    permission: "PLAYER_CAPABILITY",
    mutatesState: true,
    hostModelAccess: "NONE",
    description: "Inspect one object visible to the actor. It may mark observation/unlock an assigned clue, but can never expose another player's private payload.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["sessionId", "playerId", "objectId", "actionToken", "expectedRevision"],
      properties: {
        sessionId: id,
        playerId: id,
        objectId: id,
        focusTag: { type: "string", minLength: 1, maxLength: 40, pattern: "^[A-Z0-9_]+$" },
        actionToken: capability,
        expectedRevision: revision,
      },
    },
  },
  {
    name: "use_item",
    permission: "PLAYER_CAPABILITY",
    mutatesState: true,
    hostModelAccess: "NONE",
    description: "Use one accessible item on an engine-listed object/action. Plausible prose is never sufficient compatibility.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["sessionId", "playerId", "itemInstanceId", "targetObjectId", "actionToken", "expectedRevision"],
      properties: {
        sessionId: id,
        playerId: id,
        itemInstanceId: id,
        targetObjectId: id,
        actionToken: capability,
        expectedRevision: revision,
      },
    },
  },
  {
    name: "combine_items",
    permission: "PLAYER_CAPABILITY",
    mutatesState: true,
    hostModelAccess: "NONE",
    description: "Atomically validate an exact item multiset/state recipe, reserve inputs and create the pinned output item.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["sessionId", "playerId", "itemInstanceIds", "recipeToken", "expectedRevision"],
      properties: {
        sessionId: id,
        playerId: id,
        itemInstanceIds: { type: "array", minItems: 2, maxItems: 6, uniqueItems: true, items: id },
        recipeToken: capability,
        expectedRevision: revision,
      },
    },
  },
  {
    name: "submit_answer",
    permission: "PLAYER_CAPABILITY",
    mutatesState: true,
    hostModelAccess: "NONE",
    description: "Submit a typed answer to the strict deterministic validator. The tool never calls an LLM to determine correctness.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["sessionId", "playerId", "puzzleId", "answer", "answerToken", "expectedRevision"],
      properties: {
        sessionId: id,
        playerId: id,
        puzzleId: id,
        answer: {
          oneOf: [
            { type: "object", additionalProperties: false, required: ["type", "code"], properties: { type: { const: "EXACT_CODE" }, code: { type: "string", maxLength: 32 } } },
            { type: "object", additionalProperties: false, required: ["type", "text", "locale"], properties: { type: { const: "NORMALIZED_TEXT" }, text: { type: "string", maxLength: 200 }, locale: { type: "string", maxLength: 12 } } },
            { type: "object", additionalProperties: false, required: ["type", "elements"], properties: { type: { enum: ["ORDERED_SEQUENCE", "SET_EQUALITY"] }, elements: { type: "array", minItems: 1, maxItems: 20, items: { type: "string", maxLength: 64 } } } },
            { type: "object", additionalProperties: false, required: ["type", "value"], properties: { type: { const: "NUMERIC_TOLERANCE" }, value: { type: "number" }, unit: { type: "string", maxLength: 16 } } },
            { type: "object", additionalProperties: false, required: ["type", "itemInstanceIds"], properties: { type: { const: "ITEM_COMBINATION" }, itemInstanceIds: { type: "array", minItems: 2, maxItems: 6, uniqueItems: true, items: id } } },
            { type: "object", additionalProperties: false, required: ["type", "actionKey", "parameters"], properties: { type: { const: "STATE_CONDITION" }, actionKey: id, parameters: { type: "object", maxProperties: 12, additionalProperties: { type: ["string", "number", "boolean"] } } } },
            { type: "object", additionalProperties: false, required: ["type", "transitionKey", "input"], properties: { type: { const: "MULTI_STEP" }, transitionKey: id, input: { type: ["string", "number", "boolean"] } } }
          ]
        },
        answerToken: capability,
        expectedRevision: revision,
      },
    },
  },
  {
    name: "request_hint",
    permission: "PLAYER_CAPABILITY",
    mutatesState: true,
    hostModelAccess: "NONE",
    description: "Request a hint for one currently visible puzzle. The engine selects/authorizes the maximum safe tier and audience; final assist requires unanimous consent.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["sessionId", "playerId", "puzzleId", "requestedTier", "hintToken", "expectedRevision"],
      properties: {
        sessionId: id,
        playerId: id,
        puzzleId: id,
        requestedTier: { enum: ["DIRECTION", "STRONGER_CLUE", "NEAR_SOLUTION", "FINAL_ASSIST"] },
        unanimousConsentIds: { type: "array", minItems: 3, maxItems: 3, uniqueItems: true, items: id },
        hintToken: capability,
        expectedRevision: revision,
      },
    },
  },
  {
    name: "unlock_object",
    permission: "ENGINE_ONLY",
    mutatesState: true,
    hostModelAccess: "NONE",
    description: "Apply an object unlock already emitted by a solved puzzle effect; arbitrary object IDs cannot be supplied by a model/player.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["sessionId", "objectId", "effectToken", "expectedRevision"],
      properties: { sessionId: id, objectId: id, effectToken: capability, expectedRevision: revision },
    },
  },
  {
    name: "advance_puzzle",
    permission: "ENGINE_ONLY",
    mutatesState: true,
    hostModelAccess: "NONE",
    description: "Transition one puzzle/node using a validator result or final-assist capability and recompute graph availability.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["sessionId", "puzzleId", "targetStatus", "resolutionToken", "expectedRevision"],
      properties: {
        sessionId: id,
        puzzleId: id,
        targetStatus: { enum: ["IN_PROGRESS", "SOLVED", "ASSISTED_SOLVE"] },
        resolutionToken: capability,
        expectedRevision: revision,
      },
    },
  },
  {
    name: "check_completion",
    permission: "PARTICIPANT_PUBLIC",
    mutatesState: false,
    hostModelAccess: "READ_ONLY",
    description: "Evaluate the committed graph/final node and return completion status without solution metadata.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["sessionId", "expectedRevision"],
      properties: { sessionId: id, expectedRevision: revision },
    },
  },
  {
    name: "record_observation",
    permission: "PLAYER_CAPABILITY",
    mutatesState: true,
    hostModelAccess: "NONE",
    description: "Add a player-authored shared/private note linked to visible object IDs. Notes never solve puzzles or become canonical truth.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["sessionId", "playerId", "text", "visibility", "observationToken", "expectedRevision"],
      properties: {
        sessionId: id,
        playerId: id,
        text: { type: "string", minLength: 1, maxLength: 500 },
        linkedObjectIds: { type: "array", maxItems: 8, uniqueItems: true, items: id },
        visibility: { enum: ["PUBLIC", "SELF"] },
        assumptionTag: { type: "string", maxLength: 40, pattern: "^[A-Z0-9_]+$" },
        observationToken: capability,
        expectedRevision: revision,
      },
    },
  },
];

export interface EscapeToolResult<T = unknown> {
  ok: boolean;
  sessionId: string;
  revision: number;
  data?: T;
  error?: {
    code:
      | "UNAUTHORIZED"
      | "PRIVATE_VIEW_FORBIDDEN"
      | "STALE_REVISION"
      | "INVALID_CAPABILITY"
      | "CAPABILITY_REPLAYED"
      | "PUZZLE_LOCKED"
      | "INVALID_ANSWER_FORMAT"
      | "INCORRECT"
      | "RATE_LIMITED"
      | "ITEM_UNAVAILABLE"
      | "HINT_TIER_LOCKED"
      | "NOT_FOUND";
    message: string;
    currentRevision?: number;
  };
}
