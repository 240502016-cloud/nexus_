-- AI Board Game / The Last Portal — PostgreSQL 15+
-- UUID generation is already expected from pgcrypto in production migrations.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE game_rooms (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    server_id           BIGINT NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    channel_id          BIGINT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    host_user_id        BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    game_key            TEXT NOT NULL DEFAULT 'THE_LAST_PORTAL',
    rules_version       TEXT NOT NULL DEFAULT 'last-portal-v1',
    content_version     TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'LOBBY'
                        CHECK (status IN ('LOBBY', 'OBJECTIVE_SELECTION', 'ACTIVE', 'COMPLETED', 'CANCELLED', 'ABANDONED')),
    max_players         SMALLINT NOT NULL DEFAULT 3 CHECK (max_players = 3),
    lobby_revision      BIGINT NOT NULL DEFAULT 0 CHECK (lobby_revision >= 0),
    invite_code_hash    BYTEA,
    invite_expires_at   TIMESTAMPTZ,
    settings            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((invite_code_hash IS NULL) = (invite_expires_at IS NULL)),
    CHECK (jsonb_typeof(settings) = 'object')
);

CREATE INDEX ix_game_rooms_server_status ON game_rooms (server_id, status, created_at DESC);
CREATE INDEX ix_game_rooms_channel_status ON game_rooms (channel_id, status);

CREATE TABLE game_players (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id             UUID NOT NULL REFERENCES game_rooms(id) ON DELETE CASCADE,
    user_id             BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    seat                SMALLINT NOT NULL CHECK (seat BETWEEN 0 AND 2),
    ready               BOOLEAN NOT NULL DEFAULT FALSE,
    connection_status   TEXT NOT NULL DEFAULT 'OFFLINE'
                        CHECK (connection_status IN ('ONLINE', 'OFFLINE', 'LEFT')),
    joined_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at        TIMESTAMPTZ,
    disconnected_at     TIMESTAMPTZ,
    left_at             TIMESTAMPTZ,
    final_score         INTEGER,
    final_rank          SMALLINT CHECK (final_rank BETWEEN 1 AND 3),
    UNIQUE (room_id, user_id),
    UNIQUE (room_id, seat)
);

CREATE INDEX ix_game_players_user_active ON game_players (user_id, connection_status);

-- Immutable snapshots. Only one row per game is marked current; older revisions
-- make replay, diagnosis and deterministic verification possible.
CREATE TABLE game_states (
    id                  BIGSERIAL PRIMARY KEY,
    game_id             UUID NOT NULL REFERENCES game_rooms(id) ON DELETE CASCADE,
    revision            BIGINT NOT NULL CHECK (revision >= 0),
    state_status        TEXT NOT NULL CHECK (state_status IN ('OBJECTIVE_SELECTION', 'ACTIVE', 'COMPLETED')),
    round_number        SMALLINT NOT NULL CHECK (round_number BETWEEN 0 AND 8),
    active_player_id    UUID REFERENCES game_players(id) ON DELETE RESTRICT,
    public_state        JSONB NOT NULL,
    engine_state        JSONB NOT NULL,
    rng_algorithm       TEXT NOT NULL DEFAULT 'HMAC_SHA256_COUNTER_V1',
    rng_seed_commitment TEXT NOT NULL,
    rng_seed_ciphertext BYTEA NOT NULL,
    rng_counter         BIGINT NOT NULL DEFAULT 0 CHECK (rng_counter >= 0),
    is_current          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (game_id, revision),
    CHECK (jsonb_typeof(public_state) = 'object'),
    CHECK (jsonb_typeof(engine_state) = 'object')
);

CREATE UNIQUE INDEX uq_game_states_current ON game_states (game_id) WHERE is_current;
CREATE INDEX ix_game_states_history ON game_states (game_id, revision DESC);

CREATE TABLE game_turns (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id             UUID NOT NULL REFERENCES game_rooms(id) ON DELETE CASCADE,
    round_number        SMALLINT NOT NULL CHECK (round_number BETWEEN 1 AND 8),
    turn_index          SMALLINT NOT NULL CHECK (turn_index BETWEEN 0 AND 2),
    player_id           UUID NOT NULL REFERENCES game_players(id) ON DELETE RESTRICT,
    start_revision      BIGINT NOT NULL,
    end_revision        BIGINT,
    action_points_start SMALLINT NOT NULL DEFAULT 2 CHECK (action_points_start = 2),
    action_points_end   SMALLINT CHECK (action_points_end BETWEEN 0 AND 2),
    status              TEXT NOT NULL DEFAULT 'ACTIVE'
                        CHECK (status IN ('ACTIVE', 'COMPLETED', 'TIMED_OUT')),
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    deadline_at         TIMESTAMPTZ NOT NULL,
    ended_at            TIMESTAMPTZ,
    UNIQUE (game_id, round_number, turn_index)
);

CREATE UNIQUE INDEX uq_game_turns_one_active ON game_turns (game_id) WHERE status = 'ACTIVE';

CREATE TABLE game_actions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id             UUID NOT NULL REFERENCES game_rooms(id) ON DELETE CASCADE,
    turn_id             UUID REFERENCES game_turns(id) ON DELETE RESTRICT,
    actor_player_id     UUID NOT NULL REFERENCES game_players(id) ON DELETE RESTRICT,
    idempotency_key     TEXT NOT NULL,
    action_kind         TEXT NOT NULL,
    request_payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
    expected_revision   BIGINT NOT NULL CHECK (expected_revision >= 0),
    applied_revision    BIGINT,
    status              TEXT NOT NULL DEFAULT 'PENDING'
                        CHECK (status IN ('PENDING', 'APPLIED', 'REJECTED')),
    rejection_code      TEXT,
    result_payload      JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at         TIMESTAMPTZ,
    UNIQUE (game_id, actor_player_id, idempotency_key),
    CHECK (jsonb_typeof(request_payload) = 'object'),
    CHECK (result_payload IS NULL OR jsonb_typeof(result_payload) = 'object')
);

CREATE INDEX ix_game_actions_game_revision ON game_actions (game_id, applied_revision);
CREATE INDEX ix_game_actions_pending ON game_actions (status, created_at) WHERE status = 'PENDING';

-- Card instances. Built-in rules reference immutable definition_key values; generated
-- title/description never replace effect_spec after the instance is created.
CREATE TABLE game_cards (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id             UUID NOT NULL REFERENCES game_rooms(id) ON DELETE CASCADE,
    definition_key      TEXT NOT NULL,
    card_kind           TEXT NOT NULL CHECK (card_kind IN ('OPPORTUNITY', 'WORLD', 'PACT', 'TWIST')),
    zone                TEXT NOT NULL CHECK (zone IN ('DECK', 'HAND', 'DISCARD', 'BOARD', 'RESOLVED')),
    owner_player_id     UUID REFERENCES game_players(id) ON DELETE RESTRICT,
    deck_position       SMALLINT,
    title               TEXT NOT NULL,
    description         TEXT NOT NULL,
    effect_template     TEXT NOT NULL,
    effect_parameters   JSONB NOT NULL DEFAULT '{}'::jsonb,
    balance_budget      SMALLINT NOT NULL CHECK (balance_budget BETWEEN 1 AND 3),
    generated           BOOLEAN NOT NULL DEFAULT FALSE,
    lore_reference_ids  JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(effect_parameters) = 'object'),
    CHECK (jsonb_typeof(lore_reference_ids) = 'array'),
    CHECK ((zone = 'HAND') = (owner_player_id IS NOT NULL) OR zone <> 'HAND')
);

CREATE UNIQUE INDEX uq_game_cards_deck_position
    ON game_cards (game_id, card_kind, deck_position) WHERE deck_position IS NOT NULL;
CREATE INDEX ix_game_cards_owner_zone ON game_cards (owner_player_id, zone);

CREATE TABLE game_events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id             UUID NOT NULL REFERENCES game_rooms(id) ON DELETE CASCADE,
    sequence            BIGINT NOT NULL CHECK (sequence > 0),
    revision            BIGINT NOT NULL CHECK (revision >= 0),
    action_id           UUID REFERENCES game_actions(id) ON DELETE SET NULL,
    actor_player_id     UUID REFERENCES game_players(id) ON DELETE RESTRICT,
    event_type          TEXT NOT NULL,
    audience            TEXT NOT NULL CHECK (audience = 'PUBLIC' OR audience = 'SYSTEM' OR audience LIKE 'PLAYER:%'),
    payload             JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (game_id, sequence),
    CHECK (jsonb_typeof(payload) = 'object')
);

CREATE INDEX ix_game_events_replay ON game_events (game_id, sequence);
CREATE INDEX ix_game_events_revision ON game_events (game_id, revision);

CREATE TABLE secret_objectives (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id             UUID NOT NULL REFERENCES game_rooms(id) ON DELETE CASCADE,
    player_id           UUID NOT NULL REFERENCES game_players(id) ON DELETE CASCADE,
    template_key        TEXT NOT NULL,
    parameters          JSONB NOT NULL DEFAULT '{}'::jsonb,
    title               TEXT NOT NULL,
    description         TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'OFFERED'
                        CHECK (status IN ('OFFERED', 'SELECTED', 'COMPLETED', 'FAILED', 'DISCARDED')),
    progress            SMALLINT NOT NULL DEFAULT 0 CHECK (progress >= 0),
    target              SMALLINT NOT NULL CHECK (target > 0),
    fame_reward         SMALLINT NOT NULL DEFAULT 3 CHECK (fame_reward = 3),
    revealed_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(parameters) = 'object')
);

CREATE UNIQUE INDEX uq_secret_objective_selected
    ON secret_objectives (game_id, player_id) WHERE status IN ('SELECTED', 'COMPLETED', 'FAILED');

-- Includes narrations and pre-generated cosmetic card/event skins. The deterministic
-- effect exists before generation and is revalidated before status can become READY.
CREATE TABLE generated_content (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id             UUID NOT NULL REFERENCES game_rooms(id) ON DELETE CASCADE,
    source_event_id     UUID REFERENCES game_events(id) ON DELETE CASCADE,
    content_kind        TEXT NOT NULL CHECK (content_kind IN ('ACTION_NARRATION', 'ROUND_RECAP', 'CARD_SKIN', 'EVENT_SKIN', 'END_RECAP')),
    locale              TEXT NOT NULL DEFAULT 'tr-TR',
    status              TEXT NOT NULL DEFAULT 'PENDING'
                        CHECK (status IN ('PENDING', 'PROCESSING', 'READY', 'REJECTED', 'FALLBACK')),
    deterministic_effect JSONB,
    generated_payload   JSONB,
    lore_reference_ids  JSONB NOT NULL DEFAULT '[]'::jsonb,
    model_profile       TEXT NOT NULL DEFAULT 'board_game_narrator',
    model_name          TEXT,
    prompt_version      TEXT NOT NULL,
    input_fingerprint   TEXT NOT NULL,
    attempts            SMALLINT NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 3),
    lease_owner         TEXT,
    lease_expires_at    TIMESTAMPTZ,
    error_code          TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    UNIQUE (game_id, content_kind, input_fingerprint, locale),
    CHECK (deterministic_effect IS NULL OR jsonb_typeof(deterministic_effect) = 'object'),
    CHECK (generated_payload IS NULL OR jsonb_typeof(generated_payload) = 'object'),
    CHECK (jsonb_typeof(lore_reference_ids) = 'array')
);

CREATE INDEX ix_generated_content_claim
    ON generated_content (status, lease_expires_at, created_at)
    WHERE status IN ('PENDING', 'PROCESSING');

CREATE TABLE game_results (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id             UUID NOT NULL UNIQUE REFERENCES game_rooms(id) ON DELETE CASCADE,
    group_outcome       TEXT NOT NULL CHECK (group_outcome IN ('PORTAL_OPENED', 'ROUGH_ESCAPE')),
    winner_player_id    UUID NOT NULL REFERENCES game_players(id) ON DELETE RESTRICT,
    end_reason          TEXT NOT NULL CHECK (end_reason IN ('PORTAL_OPENED', 'CHAOS_LIMIT', 'ROUND_LIMIT')),
    final_scores        JSONB NOT NULL,
    tie_break_applied   TEXT CHECK (tie_break_applied IN ('CONTRIBUTION', 'OBJECTIVES', 'RESOURCES', 'FEWER_BETRAYALS', 'COMMITTED_RNG')),
    rng_seed_reveal     TEXT NOT NULL,
    rng_verification    JSONB NOT NULL,
    highlight_payload   JSONB,
    completed_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(final_scores) = 'array'),
    CHECK (jsonb_typeof(rng_verification) = 'object'),
    CHECK (highlight_payload IS NULL OR jsonb_typeof(highlight_payload) = 'object')
);

-- The start transaction must lock the room, verify ACTIVE membership of exactly
-- three distinct users, seats {0,1,2}, all ready, and server membership. PostgreSQL
-- CHECK constraints cannot express those cross-row invariants.
--
-- Each command transaction:
--   1. INSERT game_actions using Idempotency-Key (return prior result on conflict).
--   2. SELECT the current game_states row FOR UPDATE.
--   3. Verify actor, turn, capability, expected revision, legal action and costs.
--   4. Run the pure reducer and effect interpreter using pinned rules/content.
--   5. Mark old snapshot non-current; insert revision + 1 snapshot.
--   6. Append privacy-labelled game_events and mark the action APPLIED.
--   7. COMMIT; only then broadcast personalized WebSocket events and enqueue narration.
--
-- `engine_state`, RNG ciphertext, other players' cards/objectives and PLAYER:* events
-- are backend-only. They must never be placed in generic serializers or broadcast
-- through the shared presence gateway.
