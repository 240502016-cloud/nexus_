/**
 * Tool contracts for the AI Board Game orchestrator.
 *
 * The model normally receives only read/narration tools. Mutation tools require
 * a short-lived opaque capability minted by the deterministic engine for an
 * already selected legal action or an already resolved effect. A valid shape is
 * never sufficient authorization: every call rechecks membership, active turn,
 * capability subject, expected revision, cost and engine invariants.
 */

export type JsonSchema = Record<string, unknown>;

const id = { type: "string", minLength: 1, maxLength: 128 } as const;
const revision = { type: "integer", minimum: 0 } as const;
const capability = {
  type: "string",
  minLength: 32,
  maxLength: 2048,
  description: "Single-use, short-lived engine capability bound to game, actor, operation and revision.",
} as const;

export interface GameToolDefinition {
  name: string;
  description: string;
  mutatesState: boolean;
  availability: "MODEL_READ" | "MODEL_PRESENTATION" | "ENGINE_CAPABILITY_ONLY";
  inputSchema: JsonSchema;
}

export const GAME_TOOLS: GameToolDefinition[] = [
  {
    name: "get_game_state",
    description: "Return a privacy-filtered snapshot for the authenticated viewer. Never returns another player's hand, objective, hidden choice or RNG seed.",
    mutatesState: false,
    availability: "MODEL_READ",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["gameId", "viewerPlayerId"],
      properties: {
        gameId: id,
        viewerPlayerId: id,
        expectedMinimumRevision: revision,
      },
    },
  },
  {
    name: "list_legal_actions",
    description: "List engine-computed actions for the authenticated active player at one revision. The model must not invent actions outside this list.",
    mutatesState: false,
    availability: "MODEL_READ",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["gameId", "playerId", "expectedRevision"],
      properties: { gameId: id, playerId: id, expectedRevision: revision },
    },
  },
  {
    name: "move_player",
    description: "Apply a player-selected MOVE already authorized by a legal-action capability.",
    mutatesState: true,
    availability: "ENGINE_CAPABILITY_ONLY",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["gameId", "playerId", "destinationTileId", "actionToken", "expectedRevision"],
      properties: {
        gameId: id,
        playerId: id,
        destinationTileId: id,
        actionToken: capability,
        expectedRevision: revision,
      },
    },
  },
  {
    name: "draw_card",
    description: "Draw the next card from the committed deck order using an engine-issued draw capability.",
    mutatesState: true,
    availability: "ENGINE_CAPABILITY_ONLY",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["gameId", "deck", "drawToken", "expectedRevision"],
      properties: {
        gameId: id,
        deck: { enum: ["OPPORTUNITY", "WORLD", "PACT", "TWIST"] },
        drawToken: capability,
        expectedRevision: revision,
      },
    },
  },
  {
    name: "resolve_event",
    description: "Resolve a pending event with an engine-produced resolution capability and an allowed choice.",
    mutatesState: true,
    availability: "ENGINE_CAPABILITY_ONLY",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["gameId", "eventId", "resolutionToken", "expectedRevision"],
      properties: {
        gameId: id,
        eventId: id,
        choiceId: id,
        resolutionToken: capability,
        expectedRevision: revision,
      },
    },
  },
  {
    name: "modify_resource",
    description: "Apply one exact resource delta emitted by the effect interpreter. Not available as an unconstrained model command.",
    mutatesState: true,
    availability: "ENGINE_CAPABILITY_ONLY",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["gameId", "playerId", "resource", "delta", "effectToken", "expectedRevision"],
      properties: {
        gameId: id,
        playerId: id,
        resource: { enum: ["ENERGY", "SCRAP", "FAME", "SHIELD", "MOMENTUM"] },
        delta: { type: "integer", minimum: -6, maximum: 6 },
        effectToken: capability,
        expectedRevision: revision,
      },
    },
  },
  {
    name: "apply_status",
    description: "Apply one allowlisted status with engine-bounded duration and stacks.",
    mutatesState: true,
    availability: "ENGINE_CAPABILITY_ONLY",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["gameId", "playerId", "statusTemplateId", "durationRounds", "effectToken", "expectedRevision"],
      properties: {
        gameId: id,
        playerId: id,
        statusTemplateId: { enum: ["DISTRUSTED", "EXHAUSTED", "INSPIRED", "SHIELDED"] },
        durationRounds: { type: "integer", minimum: 1, maximum: 2 },
        stacks: { type: "integer", minimum: 1, maximum: 1, default: 1 },
        effectToken: capability,
        expectedRevision: revision,
      },
    },
  },
  {
    name: "record_choice",
    description: "Record an authenticated player's allowed public or sealed choice; reveal timing is controlled by the engine.",
    mutatesState: true,
    availability: "ENGINE_CAPABILITY_ONLY",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["gameId", "playerId", "choiceId", "optionId", "choiceToken", "expectedRevision"],
      properties: {
        gameId: id,
        playerId: id,
        choiceId: id,
        optionId: id,
        choiceToken: capability,
        expectedRevision: revision,
      },
    },
  },
  {
    name: "end_turn",
    description: "End only the authenticated active player's current turn using a legal-action capability.",
    mutatesState: true,
    availability: "ENGINE_CAPABILITY_ONLY",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["gameId", "playerId", "turnId", "actionToken", "expectedRevision"],
      properties: {
        gameId: id,
        playerId: id,
        turnId: id,
        actionToken: capability,
        expectedRevision: revision,
      },
    },
  },
  {
    name: "check_win_condition",
    description: "Evaluate the pinned rules against authoritative state. It is pure unless the engine supplies a finalize capability.",
    mutatesState: false,
    availability: "MODEL_READ",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["gameId", "expectedRevision"],
      properties: { gameId: id, expectedRevision: revision },
    },
  },
  {
    name: "fetch_relevant_lore",
    description: "Fetch consented, low-sensitivity Party Lore for cosmetic flavor. Results contain aliases and safe summaries, not raw messages or private metadata.",
    mutatesState: false,
    availability: "MODEL_READ",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["serverId", "gameId", "playerIds", "theme"],
      properties: {
        serverId: { type: "integer", minimum: 1 },
        gameId: id,
        playerIds: { type: "array", minItems: 1, maxItems: 3, uniqueItems: true, items: id },
        theme: { type: "string", minLength: 1, maxLength: 64 },
        maxItems: { type: "integer", minimum: 0, maximum: 3, default: 2 },
        usage: { const: "BOARD_GAME_FLAVOR" },
      },
    },
  },
  {
    name: "narrate_result",
    description: "Create presentation text from already committed public log entries. It cannot change, reinterpret or hide mechanical outcomes.",
    mutatesState: false,
    availability: "MODEL_PRESENTATION",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["gameId", "logEntryIds", "style", "language"],
      properties: {
        gameId: id,
        logEntryIds: { type: "array", minItems: 1, maxItems: 12, uniqueItems: true, items: id },
        style: { enum: ["COMPACT", "DRAMATIC", "PLAYFUL"] },
        language: { type: "string", pattern: "^[a-z]{2}(-[A-Z]{2})?$" },
        allowedLoreReferenceIds: {
          type: "array",
          maxItems: 3,
          uniqueItems: true,
          items: id,
        },
      },
    },
  },
];

export interface ToolResult<T = unknown> {
  ok: boolean;
  gameId: string;
  revision: number;
  data?: T;
  error?: {
    code:
      | "UNAUTHORIZED"
      | "STALE_REVISION"
      | "INVALID_CAPABILITY"
      | "CAPABILITY_REPLAYED"
      | "NOT_ACTIVE_PLAYER"
      | "ILLEGAL_ACTION"
      | "INVARIANT_VIOLATION"
      | "NOT_FOUND"
      | "RATE_LIMITED";
    message: string;
    currentRevision?: number;
  };
}

/**
 * Capability payload before server-side signing. The signed token is one-use,
 * expires within 30 seconds and is atomically consumed in the state transaction.
 */
export interface EngineCapabilityClaims {
  capabilityId: string;
  gameId: string;
  playerId?: string;
  operation: string;
  boundArgumentsHash: string;
  revision: number;
  expiresAt: string;
}
