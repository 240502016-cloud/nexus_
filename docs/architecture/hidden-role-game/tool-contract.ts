/** Tool and permission contracts for Three Seals Protocol. */

export type JsonSchema = Record<string, unknown>;

type Permission =
  | "PARTICIPANT_PUBLIC"
  | "AUTHENTICATED_SELF"
  | "ACTIVE_PLAYER_CAPABILITY"
  | "ENGINE_RESOLVER_ONLY"
  | "POST_GAME_ONLY";

export interface HiddenRoleToolDefinition {
  name: string;
  permission: Permission;
  mutatesState: boolean;
  modelAvailability: "PUBLIC_MODERATOR" | "PRIVATE_ASSISTANT" | "NONE";
  description: string;
  inputSchema: JsonSchema;
}

const id = { type: "string", minLength: 1, maxLength: 128 } as const;
const revision = { type: "integer", minimum: 0 } as const;
const capability = {
  type: "string",
  minLength: 32,
  maxLength: 2048,
  description: "Single-use signed engine capability bound to game, player, operation, arguments, phase and revision.",
} as const;

export const HIDDEN_ROLE_TOOLS: HiddenRoleToolDefinition[] = [
  {
    name: "get_public_state",
    permission: "PARTICIPANT_PUBLIC",
    mutatesState: false,
    modelAvailability: "PUBLIC_MODERATOR",
    description: "Return only the shared allowlist projection. During play, even server spectators cannot use this endpoint.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["gameId"],
      properties: { gameId: id, minimumRevision: revision },
    },
  },
  {
    name: "get_private_player_state",
    permission: "AUTHENTICATED_SELF",
    mutatesState: false,
    modelAvailability: "PRIVATE_ASSISTANT",
    description: "Return public state plus only the authenticated player's office, mandate, objective, clue, vote and legal actions.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["gameId", "playerId"],
      properties: { gameId: id, playerId: id, minimumRevision: revision },
    },
  },
  {
    name: "submit_action",
    permission: "ACTIVE_PLAYER_CAPABILITY",
    mutatesState: true,
    modelAvailability: "NONE",
    description: "Apply one engine-listed generic action. Natural-language parsing may suggest a legal action, but the player must confirm its structured parameters.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["gameId", "playerId", "actionId", "parameters", "actionToken", "expectedRevision"],
      properties: {
        gameId: id,
        playerId: id,
        actionId: id,
        parameters: { type: "object", maxProperties: 8, additionalProperties: true },
        actionToken: capability,
        expectedRevision: revision,
      },
    },
  },
  {
    name: "inspect_target",
    permission: "ACTIVE_PLAYER_CAPABILITY",
    mutatesState: true,
    modelAvailability: "NONE",
    description: "Consume an inspection action and deliver a bounded clue about evidence or claim consistency. It can never return a role, mandate, objective or another player's private clue.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["gameId", "playerId", "targetType", "targetId", "actionToken", "expectedRevision"],
      properties: {
        gameId: id,
        playerId: id,
        targetType: { enum: ["EVIDENCE", "PUBLIC_CLAIM"] },
        targetId: id,
        actionToken: capability,
        expectedRevision: revision,
      },
    },
  },
  {
    name: "create_claim",
    permission: "ACTIVE_PLAYER_CAPABILITY",
    mutatesState: true,
    modelAvailability: "NONE",
    description: "Create one structured public evidence claim or accusation. Free text is flavor only and is length/moderation checked.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["gameId", "playerId", "kind", "claimToken", "expectedRevision"],
      properties: {
        gameId: id,
        playerId: id,
        kind: { enum: ["EVIDENCE", "ACCUSATION"] },
        subjectOptionId: id,
        proposition: { enum: ["SUPPORTS_SAFE", "EXCLUDES_SAFE", "RISK_HIGH", "RISK_LOW"] },
        targetPlayerId: id,
        guessedOffice: { enum: ["SENTINEL", "ARCHIVIST", "ENVOY"] },
        guessedMandate: { enum: ["SEAL", "REVEAL", "REDIRECT"] },
        flavorText: { type: "string", maxLength: 240 },
        reputationStake: { type: "integer", enum: [0, 1] },
        claimToken: capability,
        expectedRevision: revision,
      },
      allOf: [
        {
          if: { properties: { kind: { const: "EVIDENCE" } } },
          then: { required: ["subjectOptionId", "proposition"] },
        },
        {
          if: { properties: { kind: { const: "ACCUSATION" } } },
          then: { required: ["targetPlayerId", "reputationStake"], anyOf: [{ required: ["guessedOffice"] }, { required: ["guessedMandate"] }] },
        },
      ],
    },
  },
  {
    name: "cast_vote",
    permission: "ACTIVE_PLAYER_CAPABILITY",
    mutatesState: true,
    modelAvailability: "NONE",
    description: "Store only the authenticated player's sealed vote. Returns receipt metadata, never the option in public events before resolution.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["gameId", "roundId", "playerId", "optionId", "voteToken", "expectedRevision"],
      properties: {
        gameId: id,
        roundId: id,
        playerId: id,
        optionId: id,
        voteToken: capability,
        expectedRevision: revision,
      },
    },
  },
  {
    name: "resolve_round",
    permission: "ENGINE_RESOLVER_ONLY",
    mutatesState: true,
    modelAvailability: "NONE",
    description: "Deterministically resolve votes, safe option, claims, reputation, points, stability and next phase. Scheduler or transactional engine only.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["gameId", "roundId", "resolverToken", "expectedRevision"],
      properties: { gameId: id, roundId: id, resolverToken: capability, expectedRevision: revision },
    },
  },
  {
    name: "send_private_clue",
    permission: "ENGINE_RESOLVER_ONLY",
    mutatesState: true,
    modelAvailability: "NONE",
    description: "Deliver an already persisted clue ID to its bound recipient. It cannot accept arbitrary clue text or change the recipient.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["gameId", "clueId", "recipientPlayerId", "deliveryToken", "expectedRevision"],
      properties: {
        gameId: id,
        clueId: id,
        recipientPlayerId: id,
        deliveryToken: capability,
        expectedRevision: revision,
      },
    },
  },
  {
    name: "check_end_condition",
    permission: "PARTICIPANT_PUBLIC",
    mutatesState: false,
    modelAvailability: "PUBLIC_MODERATOR",
    description: "Evaluate pinned public end conditions without revealing assignments or changing state.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["gameId", "expectedRevision"],
      properties: { gameId: id, expectedRevision: revision },
    },
  },
  {
    name: "reveal_roles",
    permission: "POST_GAME_ONLY",
    mutatesState: true,
    modelAvailability: "NONE",
    description: "Publish committed offices, mandates, objectives and score breakdown only after the deterministic result has committed.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["gameId", "revealToken", "expectedRevision"],
      properties: { gameId: id, revealToken: capability, expectedRevision: revision },
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
      | "PRIVATE_STATE_FORBIDDEN"
      | "STALE_REVISION"
      | "WRONG_PHASE"
      | "INVALID_CAPABILITY"
      | "CAPABILITY_REPLAYED"
      | "INVALID_CLAIM"
      | "DUPLICATE_ACTION"
      | "NOT_FOUND";
    message: string;
    currentRevision?: number;
  };
}
