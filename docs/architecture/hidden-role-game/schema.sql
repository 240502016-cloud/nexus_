-- Three Seals Protocol — PostgreSQL 15+
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS hidden_role_game;
SET search_path TO hidden_role_game, public;

CREATE TABLE hidden_role_games (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    server_id               BIGINT NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    channel_id              BIGINT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    host_user_id            BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    rules_version           TEXT NOT NULL DEFAULT 'three-seals-v1',
    content_version         TEXT NOT NULL,
    interface_kind          TEXT NOT NULL DEFAULT 'WEB' CHECK (interface_kind IN ('WEB', 'DISCORD')),
    status                  TEXT NOT NULL DEFAULT 'LOBBY'
                            CHECK (status IN ('LOBBY', 'ROLE_DELIVERY', 'ACTIVE', 'FINAL_DEDUCTION', 'COMPLETED', 'CANCELLED')),
    phase                   TEXT CHECK (phase IN ('CLUE', 'CLAIM', 'DISCUSSION', 'VOTE', 'RESOLUTION', 'DEDUCTION')),
    revision                BIGINT NOT NULL DEFAULT 0 CHECK (revision >= 0),
    current_round           SMALLINT NOT NULL DEFAULT 0 CHECK (current_round BETWEEN 0 AND 4),
    stability               SMALLINT NOT NULL DEFAULT 4 CHECK (stability BETWEEN 0 AND 5),
    arbiter_seat            SMALLINT CHECK (arbiter_seat BETWEEN 0 AND 2),
    public_state            JSONB NOT NULL DEFAULT '{}'::jsonb,
    engine_state_ciphertext BYTEA,
    encryption_key_version  SMALLINT NOT NULL DEFAULT 1,
    seed_commitment         TEXT,
    rng_seed_ciphertext     BYTEA,
    rng_counter             BIGINT NOT NULL DEFAULT 0 CHECK (rng_counter >= 0),
    invite_code_hash        BYTEA,
    invite_expires_at       TIMESTAMPTZ,
    settings                JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at              TIMESTAMPTZ,
    completed_at            TIMESTAMPTZ,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(public_state) = 'object'),
    CHECK (jsonb_typeof(settings) = 'object'),
    CHECK ((invite_code_hash IS NULL) = (invite_expires_at IS NULL))
);

CREATE INDEX ix_hidden_role_games_server_status
    ON hidden_role_games (server_id, status, created_at DESC);
CREATE INDEX ix_hidden_role_games_channel_status
    ON hidden_role_games (channel_id, status);

CREATE TABLE hidden_role_players (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id                 UUID NOT NULL REFERENCES hidden_role_games(id) ON DELETE CASCADE,
    user_id                 BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    seat                    SMALLINT NOT NULL CHECK (seat BETWEEN 0 AND 2),
    ready                   BOOLEAN NOT NULL DEFAULT FALSE,
    secret_delivery_ready   BOOLEAN NOT NULL DEFAULT FALSE,
    connection_status       TEXT NOT NULL DEFAULT 'OFFLINE'
                            CHECK (connection_status IN ('ONLINE', 'OFFLINE', 'LEFT')),
    reputation              SMALLINT NOT NULL DEFAULT 3 CHECK (reputation BETWEEN 1 AND 5),
    public_insight          SMALLINT NOT NULL DEFAULT 0 CHECK (public_insight BETWEEN 0 AND 8),
    supported_claims        SMALLINT NOT NULL DEFAULT 0 CHECK (supported_claims BETWEEN 0 AND 4),
    contradicted_claims     SMALLINT NOT NULL DEFAULT 0 CHECK (contradicted_claims BETWEEN 0 AND 4),
    safe_votes              SMALLINT NOT NULL DEFAULT 0 CHECK (safe_votes BETWEEN 0 AND 4),
    joined_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at            TIMESTAMPTZ,
    disconnected_at         TIMESTAMPTZ,
    left_at                 TIMESTAMPTZ,
    UNIQUE (game_id, user_id),
    UNIQUE (game_id, seat)
);

CREATE INDEX ix_hidden_role_players_user ON hidden_role_players (user_id, connection_status);

-- Office and Mandate are encrypted together with application-level AES-256-GCM.
-- Commitments are SHA-256(random 256-bit salt || canonical payload). The salt stays
-- inside ciphertext until reveal; hashing a nine-value role domain without a secret
-- salt would allow assignments to be brute-forced during play.
CREATE TABLE role_assignments (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id                 UUID NOT NULL REFERENCES hidden_role_games(id) ON DELETE CASCADE,
    player_id               UUID NOT NULL UNIQUE REFERENCES hidden_role_players(id) ON DELETE CASCADE,
    assignment_ciphertext   BYTEA NOT NULL,
    assignment_commitment   TEXT NOT NULL,
    encryption_key_version  SMALLINT NOT NULL,
    revealed_office         TEXT CHECK (revealed_office IN ('SENTINEL', 'ARCHIVIST', 'ENVOY')),
    revealed_mandate        TEXT CHECK (revealed_mandate IN ('SEAL', 'REVEAL', 'REDIRECT')),
    assigned_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    revealed_at             TIMESTAMPTZ,
    UNIQUE (game_id, assignment_commitment),
    CHECK ((revealed_office IS NULL) = (revealed_mandate IS NULL)),
    CHECK ((revealed_office IS NULL) = (revealed_at IS NULL))
);

CREATE TABLE private_objectives (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id                 UUID NOT NULL REFERENCES hidden_role_games(id) ON DELETE CASCADE,
    player_id               UUID NOT NULL UNIQUE REFERENCES hidden_role_players(id) ON DELETE CASCADE,
    objective_ciphertext    BYTEA NOT NULL,
    progress_ciphertext     BYTEA NOT NULL,
    objective_commitment    TEXT NOT NULL,
    encryption_key_version  SMALLINT NOT NULL,
    status                  TEXT NOT NULL DEFAULT 'ACTIVE'
                            CHECK (status IN ('ACTIVE', 'COMPLETED', 'FAILED')),
    revealed_payload        JSONB,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    revealed_at             TIMESTAMPTZ,
    CHECK (revealed_payload IS NULL OR jsonb_typeof(revealed_payload) = 'object'),
    CHECK ((revealed_payload IS NULL) = (revealed_at IS NULL))
);

CREATE TABLE public_actions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id                 UUID NOT NULL REFERENCES hidden_role_games(id) ON DELETE CASCADE,
    round_number            SMALLINT NOT NULL CHECK (round_number BETWEEN 1 AND 4),
    actor_player_id         UUID NOT NULL REFERENCES hidden_role_players(id) ON DELETE RESTRICT,
    idempotency_key         TEXT NOT NULL,
    action_kind             TEXT NOT NULL CHECK (action_kind IN ('CREATE_CLAIM', 'RETRACT_CLAIM', 'REQUEST_RULE', 'PASS')),
    payload                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    expected_revision       BIGINT NOT NULL,
    applied_revision        BIGINT NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (game_id, actor_player_id, idempotency_key),
    CHECK (jsonb_typeof(payload) = 'object')
);

CREATE INDEX ix_public_actions_replay ON public_actions (game_id, applied_revision, created_at);

CREATE TABLE private_actions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id                 UUID NOT NULL REFERENCES hidden_role_games(id) ON DELETE CASCADE,
    round_number            SMALLINT NOT NULL CHECK (round_number BETWEEN 1 AND 4),
    actor_player_id         UUID NOT NULL REFERENCES hidden_role_players(id) ON DELETE RESTRICT,
    idempotency_key         TEXT NOT NULL,
    action_kind             TEXT NOT NULL CHECK (action_kind IN ('INSPECT', 'CAST_VOTE', 'FINAL_DEDUCTION')),
    payload_ciphertext      BYTEA NOT NULL,
    payload_hash            TEXT NOT NULL,
    encryption_key_version  SMALLINT NOT NULL,
    expected_revision       BIGINT NOT NULL,
    applied_revision        BIGINT NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (game_id, actor_player_id, idempotency_key)
);

CREATE INDEX ix_private_actions_replay ON private_actions (game_id, applied_revision, created_at);

CREATE TABLE clues (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id                 UUID NOT NULL REFERENCES hidden_role_games(id) ON DELETE CASCADE,
    round_number            SMALLINT NOT NULL CHECK (round_number BETWEEN 1 AND 4),
    definition_key          TEXT NOT NULL,
    lens                    TEXT NOT NULL CHECK (lens IN ('PUBLIC', 'CONTAINMENT', 'PROVENANCE', 'CONSEQUENCE')),
    visibility              TEXT NOT NULL CHECK (visibility IN ('PUBLIC', 'PRIVATE_PLAYER')),
    owner_player_id         UUID REFERENCES hidden_role_players(id) ON DELETE CASCADE,
    public_payload          JSONB,
    private_payload_ciphertext BYTEA,
    clue_commitment         TEXT NOT NULL,
    encryption_key_version  SMALLINT,
    renderer_kind           TEXT NOT NULL DEFAULT 'TEMPLATE' CHECK (renderer_kind IN ('TEMPLATE', 'LLM_VALIDATED')),
    model_profile           TEXT,
    prompt_version          TEXT,
    delivered_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (game_id, round_number, lens),
    CHECK (public_payload IS NULL OR jsonb_typeof(public_payload) = 'object'),
    CHECK (
        (visibility = 'PUBLIC' AND owner_player_id IS NULL AND public_payload IS NOT NULL AND private_payload_ciphertext IS NULL)
        OR
        (visibility = 'PRIVATE_PLAYER' AND owner_player_id IS NOT NULL AND public_payload IS NULL AND private_payload_ciphertext IS NOT NULL)
    )
);

CREATE INDEX ix_clues_private_delivery ON clues (owner_player_id, delivered_at)
    WHERE visibility = 'PRIVATE_PLAYER';

CREATE TABLE votes (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id                 UUID NOT NULL REFERENCES hidden_role_games(id) ON DELETE CASCADE,
    round_number            SMALLINT NOT NULL CHECK (round_number BETWEEN 1 AND 4),
    player_id               UUID NOT NULL REFERENCES hidden_role_players(id) ON DELETE CASCADE,
    option_ciphertext       BYTEA NOT NULL,
    vote_commitment         TEXT NOT NULL,
    encryption_key_version  SMALLINT NOT NULL,
    revealed_option_id      TEXT CHECK (revealed_option_id IN ('A', 'B', 'C')),
    idempotency_key         TEXT NOT NULL,
    submitted_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    revealed_at             TIMESTAMPTZ,
    UNIQUE (game_id, round_number, player_id),
    UNIQUE (game_id, player_id, idempotency_key),
    CHECK ((revealed_option_id IS NULL) = (revealed_at IS NULL))
);

CREATE TABLE round_results (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id                 UUID NOT NULL REFERENCES hidden_role_games(id) ON DELETE CASCADE,
    round_number            SMALLINT NOT NULL CHECK (round_number BETWEEN 1 AND 4),
    start_revision          BIGINT NOT NULL,
    resolved_revision       BIGINT NOT NULL,
    scenario_key            TEXT NOT NULL,
    selected_option_id      TEXT NOT NULL CHECK (selected_option_id IN ('A', 'B', 'C')),
    selected_disposition    TEXT NOT NULL CHECK (selected_disposition IN ('SEAL', 'REVEAL', 'REDIRECT')),
    safe_option_id          TEXT NOT NULL CHECK (safe_option_id IN ('A', 'B', 'C')),
    was_safe                BOOLEAN NOT NULL,
    stability_delta         SMALLINT NOT NULL CHECK (stability_delta BETWEEN -2 AND 0),
    public_result           JSONB NOT NULL,
    private_score_deltas_ciphertext BYTEA NOT NULL,
    encryption_key_version  SMALLINT NOT NULL,
    resolved_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (game_id, round_number),
    CHECK (jsonb_typeof(public_result) = 'object')
);

CREATE TABLE game_results (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id                 UUID NOT NULL UNIQUE REFERENCES hidden_role_games(id) ON DELETE CASCADE,
    group_outcome           TEXT NOT NULL CHECK (group_outcome IN ('STABLE', 'FRACTURED', 'COLLAPSED')),
    winner_player_id        UUID NOT NULL REFERENCES hidden_role_players(id) ON DELETE RESTRICT,
    score_breakdown         JSONB NOT NULL,
    revealed_assignments    JSONB NOT NULL,
    revealed_objectives     JSONB NOT NULL,
    tie_break_applied       TEXT CHECK (tie_break_applied IN ('REPUTATION', 'SAFE_VOTES', 'SUPPORTED_CLAIMS', 'FEWER_CONTRADICTIONS', 'COMMITTED_RNG')),
    rng_seed_reveal         TEXT NOT NULL,
    verification_payload    JSONB NOT NULL,
    deterministic_recap     JSONB NOT NULL,
    ai_recap                JSONB,
    completed_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(score_breakdown) = 'array'),
    CHECK (jsonb_typeof(revealed_assignments) = 'array'),
    CHECK (jsonb_typeof(revealed_objectives) = 'array'),
    CHECK (jsonb_typeof(verification_payload) = 'object'),
    CHECK (jsonb_typeof(deterministic_recap) = 'object'),
    CHECK (ai_recap IS NULL OR jsonb_typeof(ai_recap) = 'object')
);

-- Encrypted audit only. Do not forward payloads to application logs, analytics,
-- exception trackers or model traces. metadata must stay content-free.
CREATE TABLE secret_logs (
    id                      BIGSERIAL PRIMARY KEY,
    game_id                 UUID NOT NULL REFERENCES hidden_role_games(id) ON DELETE CASCADE,
    sequence                BIGINT NOT NULL CHECK (sequence > 0),
    audience_player_id      UUID REFERENCES hidden_role_players(id) ON DELETE CASCADE,
    event_type              TEXT NOT NULL,
    metadata                JSONB NOT NULL DEFAULT '{}'::jsonb,
    payload_ciphertext      BYTEA NOT NULL,
    payload_hash            TEXT NOT NULL,
    encryption_key_version  SMALLINT NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (game_id, sequence),
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX ix_secret_logs_replay ON secret_logs (game_id, sequence);

-- Cross-row invariants checked inside a room row lock at start:
--   * exactly three distinct users occupy seats {0,1,2}; all are ready;
--   * web clients have fetched private delivery; Discord clients have verified DM;
--   * offices and mandates are each bijections over their three values;
--   * role/objective/clue commitments exist before any secret is delivered.
--
-- Command transaction:
--   1. Reserve Idempotency-Key in the appropriate public/private action table.
--   2. SELECT hidden_role_games FOR UPDATE and verify membership, phase, revision and capability.
--   3. Decrypt only the minimum secret records required by the pure resolver.
--   4. Apply deterministic transition; update revision/public_state/encrypted engine state.
--   5. Append public action and/or encrypted secret log, then COMMIT.
--   6. Project one shared event plus zero or more per-player private events after commit.
--
-- AES-GCM associated data binds ciphertext to table, game_id, player_id/round and
-- record id. Vote/objective/clue commitments use the same hidden-random-salt rule.
-- Keys live outside PostgreSQL, are versioned and never enter LLM prompts.

RESET search_path;
