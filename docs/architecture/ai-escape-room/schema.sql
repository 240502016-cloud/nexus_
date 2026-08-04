-- AI Escape Room / Nadir-3 — PostgreSQL 15+
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS escape_room;
SET search_path TO escape_room, public;

CREATE TABLE escape_sessions (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    server_id                   BIGINT NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    channel_id                  BIGINT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    host_user_id                BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    rules_version               TEXT NOT NULL DEFAULT 'nadir-three-v1',
    content_version             TEXT NOT NULL,
    status                      TEXT NOT NULL DEFAULT 'LOBBY'
                                CHECK (status IN ('LOBBY', 'ACTIVE', 'PAUSED', 'OVERTIME', 'COMPLETED', 'CANCELLED')),
    revision                    BIGINT NOT NULL DEFAULT 0 CHECK (revision >= 0),
    timer_mode                  TEXT NOT NULL DEFAULT 'STANDARD_45'
                                CHECK (timer_mode IN ('RELAXED', 'STANDARD_45', 'CHALLENGE_30')),
    timer_status                TEXT NOT NULL DEFAULT 'NOT_STARTED'
                                CHECK (timer_status IN ('NOT_STARTED', 'RUNNING', 'PAUSED', 'OVERTIME', 'STOPPED')),
    time_limit_seconds          INTEGER CHECK (time_limit_seconds IS NULL OR time_limit_seconds BETWEEN 600 AND 7200),
    timer_started_at            TIMESTAMPTZ,
    timer_paused_at             TIMESTAMPTZ,
    accumulated_pause_seconds   INTEGER NOT NULL DEFAULT 0 CHECK (accumulated_pause_seconds >= 0),
    room_code_hash              BYTEA,
    room_code_expires_at        TIMESTAMPTZ,
    public_state                JSONB NOT NULL DEFAULT '{}'::jsonb,
    engine_state_ciphertext     BYTEA,
    encryption_key_version      SMALLINT NOT NULL DEFAULT 1,
    seed_commitment             TEXT,
    rng_seed_ciphertext         BYTEA,
    rng_counter                 BIGINT NOT NULL DEFAULT 0 CHECK (rng_counter >= 0),
    settings                    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at                  TIMESTAMPTZ,
    paused_at                   TIMESTAMPTZ,
    completed_at                TIMESTAMPTZ,
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(public_state) = 'object'),
    CHECK (jsonb_typeof(settings) = 'object'),
    CHECK ((room_code_hash IS NULL) = (room_code_expires_at IS NULL))
);

CREATE INDEX ix_escape_sessions_server_status ON escape_sessions (server_id, status, updated_at DESC);

CREATE TABLE escape_players (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id                  UUID NOT NULL REFERENCES escape_sessions(id) ON DELETE CASCADE,
    user_id                     BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    seat                        SMALLINT NOT NULL CHECK (seat BETWEEN 0 AND 2),
    role_key                    TEXT NOT NULL CHECK (role_key IN ('ENGINEER', 'ANALYST', 'NAVIGATOR')),
    ready                       BOOLEAN NOT NULL DEFAULT FALSE,
    private_delivery_ready      BOOLEAN NOT NULL DEFAULT FALSE,
    connection_status           TEXT NOT NULL DEFAULT 'OFFLINE'
                                CHECK (connection_status IN ('ONLINE', 'OFFLINE', 'LEFT')),
    ability_charges             SMALLINT NOT NULL DEFAULT 1 CHECK (ability_charges BETWEEN 0 AND 1),
    accessibility_preferences_ciphertext BYTEA NOT NULL,
    encryption_key_version      SMALLINT NOT NULL,
    joined_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_activity_at            TIMESTAMPTZ,
    disconnected_at             TIMESTAMPTZ,
    left_at                     TIMESTAMPTZ,
    UNIQUE (session_id, user_id),
    UNIQUE (session_id, seat),
    UNIQUE (session_id, role_key)
);

CREATE TABLE room_states (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id                  UUID NOT NULL REFERENCES escape_sessions(id) ON DELETE CASCADE,
    room_key                    TEXT NOT NULL,
    display_name                TEXT NOT NULL,
    description                TEXT NOT NULL,
    discovered                  BOOLEAN NOT NULL DEFAULT FALSE,
    accessible                  BOOLEAN NOT NULL DEFAULT FALSE,
    public_state                JSONB NOT NULL DEFAULT '{}'::jsonb,
    engine_state_ciphertext     BYTEA NOT NULL,
    connected_room_keys         JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_revision            BIGINT NOT NULL,
    UNIQUE (session_id, room_key),
    CHECK (jsonb_typeof(public_state) = 'object'),
    CHECK (jsonb_typeof(connected_room_keys) = 'array')
);

CREATE TABLE room_objects (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id                  UUID NOT NULL REFERENCES escape_sessions(id) ON DELETE CASCADE,
    room_state_id               UUID NOT NULL REFERENCES room_states(id) ON DELETE CASCADE,
    definition_key              TEXT NOT NULL,
    display_name                TEXT NOT NULL,
    description                 TEXT NOT NULL,
    object_state                TEXT NOT NULL
                                CHECK (object_state IN ('HIDDEN', 'VISIBLE', 'LOCKED', 'UNLOCKED', 'OPEN', 'DISABLED')),
    visibility                  TEXT NOT NULL,
    inspectable                 BOOLEAN NOT NULL DEFAULT TRUE,
    public_properties           JSONB NOT NULL DEFAULT '{}'::jsonb,
    private_properties_ciphertext BYTEA,
    linked_puzzle_node_ids      JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_revision            BIGINT NOT NULL,
    UNIQUE (session_id, room_state_id, definition_key),
    CHECK (jsonb_typeof(public_properties) = 'object'),
    CHECK (jsonb_typeof(linked_puzzle_node_ids) = 'array')
);

CREATE TABLE puzzle_graphs (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id                  UUID NOT NULL UNIQUE REFERENCES escape_sessions(id) ON DELETE CASCADE,
    graph_version               TEXT NOT NULL,
    graph_hash                  TEXT NOT NULL,
    definition_ciphertext       BYTEA NOT NULL,
    topological_order_ciphertext BYTEA NOT NULL,
    required_node_count         SMALLINT NOT NULL CHECK (required_node_count > 0),
    optional_node_count         SMALLINT NOT NULL DEFAULT 0 CHECK (optional_node_count >= 0),
    final_node_key              TEXT NOT NULL,
    validated_at                TIMESTAMPTZ NOT NULL,
    validator_version           TEXT NOT NULL,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE puzzle_instances (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id                  UUID NOT NULL REFERENCES escape_sessions(id) ON DELETE CASCADE,
    graph_id                    UUID NOT NULL REFERENCES puzzle_graphs(id) ON DELETE CASCADE,
    node_key                    TEXT NOT NULL,
    node_kind                   TEXT NOT NULL CHECK (node_kind IN ('ENTRY', 'PARALLEL', 'GATE', 'META', 'FINAL', 'OPTIONAL')),
    template_id                 TEXT NOT NULL,
    template_version            TEXT NOT NULL,
    difficulty                  SMALLINT NOT NULL CHECK (difficulty BETWEEN 1 AND 5),
    status                      TEXT NOT NULL DEFAULT 'LOCKED'
                                CHECK (status IN ('LOCKED', 'AVAILABLE', 'IN_PROGRESS', 'SOLVED', 'ASSISTED_SOLVE')),
    public_variables            JSONB NOT NULL DEFAULT '{}'::jsonb,
    private_variables_ciphertext BYTEA,
    solution_spec_ciphertext    BYTEA NOT NULL,
    solution_commitment         TEXT NOT NULL,
    dependency_spec_ciphertext  BYTEA NOT NULL,
    attempt_policy              JSONB NOT NULL,
    required                    BOOLEAN NOT NULL DEFAULT TRUE,
    takeover_policy             TEXT NOT NULL DEFAULT 'AFTER_DISCONNECT_GRACE'
                                CHECK (takeover_policy IN ('NONE', 'AFTER_DISCONNECT_GRACE')),
    available_at                TIMESTAMPTZ,
    solved_at                   TIMESTAMPTZ,
    solved_revision             BIGINT,
    UNIQUE (session_id, node_key),
    CHECK (jsonb_typeof(public_variables) = 'object'),
    CHECK (jsonb_typeof(attempt_policy) = 'object')
);

CREATE INDEX ix_puzzle_instances_session_status ON puzzle_instances (session_id, status, node_kind);

CREATE TABLE puzzle_attempts (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id                  UUID NOT NULL REFERENCES escape_sessions(id) ON DELETE CASCADE,
    puzzle_id                   UUID NOT NULL REFERENCES puzzle_instances(id) ON DELETE CASCADE,
    player_id                   UUID NOT NULL REFERENCES escape_players(id) ON DELETE RESTRICT,
    idempotency_key             TEXT NOT NULL,
    answer_type                 TEXT NOT NULL
                                CHECK (answer_type IN ('EXACT_CODE', 'NORMALIZED_TEXT', 'ORDERED_SEQUENCE', 'SET_EQUALITY', 'NUMERIC_TOLERANCE', 'ITEM_COMBINATION', 'STATE_CONDITION', 'MULTI_STEP')),
    answer_payload_ciphertext   BYTEA NOT NULL,
    answer_payload_hash         TEXT NOT NULL,
    normalized_answer_hash      TEXT,
    validator_version           TEXT NOT NULL,
    result                      TEXT NOT NULL
                                CHECK (result IN ('CORRECT', 'INCORRECT', 'DUPLICATE', 'INVALID_FORMAT', 'RATE_LIMITED')),
    bounded_feedback_code       TEXT,
    expected_revision           BIGINT NOT NULL,
    applied_revision            BIGINT,
    submitted_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, player_id, idempotency_key)
);

CREATE INDEX ix_puzzle_attempts_rate ON puzzle_attempts (puzzle_id, player_id, submitted_at DESC);

CREATE TABLE hint_requests (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id                  UUID NOT NULL REFERENCES escape_sessions(id) ON DELETE CASCADE,
    puzzle_id                   UUID NOT NULL REFERENCES puzzle_instances(id) ON DELETE CASCADE,
    requested_by_player_id      UUID NOT NULL REFERENCES escape_players(id) ON DELETE RESTRICT,
    requested_tier              TEXT NOT NULL
                                CHECK (requested_tier IN ('DIRECTION', 'STRONGER_CLUE', 'NEAR_SOLUTION', 'FINAL_ASSIST')),
    authorized_tier             TEXT
                                CHECK (authorized_tier IN ('DIRECTION', 'STRONGER_CLUE', 'NEAR_SOLUTION', 'FINAL_ASSIST')),
    visibility                  TEXT NOT NULL,
    status                      TEXT NOT NULL DEFAULT 'PENDING'
                                CHECK (status IN ('PENDING', 'AUTHORIZED', 'DELIVERED', 'DENIED')),
    canonical_hint_ciphertext   BYTEA,
    rendered_public             TEXT,
    rendered_private_ciphertext BYTEA,
    consent_player_ids          JSONB NOT NULL DEFAULT '[]'::jsonb,
    penalty_seconds             INTEGER NOT NULL DEFAULT 0 CHECK (penalty_seconds BETWEEN 0 AND 3600),
    denial_code                 TEXT,
    requested_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at                TIMESTAMPTZ,
    CHECK (jsonb_typeof(consent_player_ids) = 'array'),
    CHECK ((visibility = 'PUBLIC' AND rendered_private_ciphertext IS NULL)
        OR (visibility <> 'PUBLIC' AND rendered_public IS NULL))
);

CREATE TABLE item_instances (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id                  UUID NOT NULL REFERENCES escape_sessions(id) ON DELETE CASCADE,
    definition_key              TEXT NOT NULL,
    display_name                TEXT NOT NULL,
    description                 TEXT NOT NULL,
    item_state                  TEXT NOT NULL DEFAULT 'AVAILABLE'
                                CHECK (item_state IN ('AVAILABLE', 'RESERVED', 'COMBINED', 'CONSUMED', 'BROKEN')),
    quantity                    SMALLINT NOT NULL DEFAULT 1 CHECK (quantity BETWEEN 0 AND 20),
    durability                  SMALLINT CHECK (durability BETWEEN 0 AND 10),
    visibility                  TEXT NOT NULL,
    source_puzzle_id            UUID REFERENCES puzzle_instances(id) ON DELETE SET NULL,
    source_object_id            UUID REFERENCES room_objects(id) ON DELETE SET NULL,
    state_properties            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_revision            BIGINT NOT NULL,
    CHECK (jsonb_typeof(state_properties) = 'object')
);

CREATE TABLE inventories (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id                  UUID NOT NULL REFERENCES escape_sessions(id) ON DELETE CASCADE,
    item_instance_id            UUID NOT NULL REFERENCES item_instances(id) ON DELETE CASCADE,
    holder_type                 TEXT NOT NULL CHECK (holder_type IN ('SHARED', 'PLAYER', 'ROOM_OBJECT')),
    holder_player_id            UUID REFERENCES escape_players(id) ON DELETE CASCADE,
    holder_object_id            UUID REFERENCES room_objects(id) ON DELETE CASCADE,
    active                      BOOLEAN NOT NULL DEFAULT TRUE,
    acquired_revision           BIGINT NOT NULL,
    released_revision           BIGINT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((holder_type = 'SHARED' AND holder_player_id IS NULL AND holder_object_id IS NULL)
        OR (holder_type = 'PLAYER' AND holder_player_id IS NOT NULL AND holder_object_id IS NULL)
        OR (holder_type = 'ROOM_OBJECT' AND holder_player_id IS NULL AND holder_object_id IS NOT NULL))
);

CREATE UNIQUE INDEX uq_inventories_active_item ON inventories (item_instance_id) WHERE active;

CREATE TABLE private_clues (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id                  UUID NOT NULL REFERENCES escape_sessions(id) ON DELETE CASCADE,
    player_id                   UUID NOT NULL REFERENCES escape_players(id) ON DELETE CASCADE,
    puzzle_id                   UUID NOT NULL REFERENCES puzzle_instances(id) ON DELETE CASCADE,
    clue_key                    TEXT NOT NULL,
    clue_payload_ciphertext     BYTEA NOT NULL,
    clue_commitment             TEXT NOT NULL,
    rendered_text_ciphertext    BYTEA NOT NULL,
    source                      TEXT NOT NULL DEFAULT 'TEMPLATE'
                                CHECK (source IN ('TEMPLATE', 'EMERGENCY_TAKEOVER')),
    revealed_to_others          BOOLEAN NOT NULL DEFAULT FALSE,
    delivered_at                TIMESTAMPTZ,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, player_id, puzzle_id, clue_key)
);

CREATE TABLE simultaneous_inputs (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id                  UUID NOT NULL REFERENCES escape_sessions(id) ON DELETE CASCADE,
    puzzle_id                   UUID NOT NULL REFERENCES puzzle_instances(id) ON DELETE CASCADE,
    player_id                   UUID NOT NULL REFERENCES escape_players(id) ON DELETE CASCADE,
    window_id                   UUID NOT NULL,
    input_ciphertext            BYTEA NOT NULL,
    input_commitment            TEXT NOT NULL,
    submitted_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    consumed                    BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (window_id, player_id)
);

CREATE INDEX ix_simultaneous_inputs_window ON simultaneous_inputs (window_id, submitted_at);

CREATE TABLE observations (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id                  UUID NOT NULL REFERENCES escape_sessions(id) ON DELETE CASCADE,
    player_id                   UUID NOT NULL REFERENCES escape_players(id) ON DELETE CASCADE,
    visibility                  TEXT NOT NULL CHECK (visibility IN ('PUBLIC', 'SELF')),
    text_public                 TEXT,
    text_private_ciphertext     BYTEA,
    linked_object_ids           JSONB NOT NULL DEFAULT '[]'::jsonb,
    assumption_tag              TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(linked_object_ids) = 'array'),
    CHECK ((visibility = 'PUBLIC' AND text_public IS NOT NULL AND text_private_ciphertext IS NULL)
        OR (visibility = 'SELF' AND text_public IS NULL AND text_private_ciphertext IS NOT NULL))
);

CREATE TABLE session_events (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id                  UUID NOT NULL REFERENCES escape_sessions(id) ON DELETE CASCADE,
    sequence                    BIGINT NOT NULL CHECK (sequence > 0),
    revision                    BIGINT NOT NULL CHECK (revision >= 0),
    audience                    TEXT NOT NULL,
    event_type                  TEXT NOT NULL,
    payload_public              JSONB,
    payload_private_ciphertext  BYTEA,
    occurred_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, sequence),
    CHECK (payload_public IS NULL OR jsonb_typeof(payload_public) = 'object'),
    CHECK ((audience = 'PUBLIC' AND payload_public IS NOT NULL AND payload_private_ciphertext IS NULL)
        OR (audience <> 'PUBLIC' AND payload_public IS NULL AND payload_private_ciphertext IS NOT NULL))
);

CREATE INDEX ix_session_events_replay ON session_events (session_id, sequence);

CREATE TABLE generated_flavor (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id                  UUID NOT NULL REFERENCES escape_sessions(id) ON DELETE CASCADE,
    puzzle_id                   UUID REFERENCES puzzle_instances(id) ON DELETE CASCADE,
    hint_request_id             UUID REFERENCES hint_requests(id) ON DELETE CASCADE,
    audience                    TEXT NOT NULL,
    content_kind                TEXT NOT NULL
                                CHECK (content_kind IN ('ROOM_FLAVOR', 'PUZZLE_WRAPPER', 'DOCUMENT', 'ITEM_LABEL', 'HINT', 'VALIDATION_REACTION', 'RECAP')),
    status                      TEXT NOT NULL DEFAULT 'PENDING'
                                CHECK (status IN ('PENDING', 'PROCESSING', 'READY', 'REJECTED', 'FALLBACK')),
    source_revision             BIGINT NOT NULL,
    input_fingerprint           TEXT NOT NULL,
    output_public               JSONB,
    output_private_ciphertext   BYTEA,
    lore_reference_ids          JSONB NOT NULL DEFAULT '[]'::jsonb,
    model_profile               TEXT NOT NULL DEFAULT 'escape_room_host',
    model_name                  TEXT,
    prompt_version              TEXT NOT NULL,
    attempts                    SMALLINT NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 3),
    lease_owner                 TEXT,
    lease_expires_at            TIMESTAMPTZ,
    error_code                  TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at                TIMESTAMPTZ,
    UNIQUE (session_id, content_kind, audience, input_fingerprint),
    CHECK (output_public IS NULL OR jsonb_typeof(output_public) = 'object'),
    CHECK (jsonb_typeof(lore_reference_ids) = 'array'),
    CHECK ((audience = 'PUBLIC' AND output_private_ciphertext IS NULL)
        OR (audience <> 'PUBLIC' AND output_public IS NULL))
);

CREATE INDEX ix_generated_flavor_claim
    ON generated_flavor (status, lease_expires_at, created_at)
    WHERE status IN ('PENDING', 'PROCESSING');

CREATE TABLE session_results (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id                  UUID NOT NULL UNIQUE REFERENCES escape_sessions(id) ON DELETE CASCADE,
    completion_status           TEXT NOT NULL CHECK (completion_status IN ('ESCAPED', 'ESCAPED_OVERTIME', 'CANCELLED')),
    elapsed_seconds             INTEGER NOT NULL CHECK (elapsed_seconds >= 0),
    paused_seconds              INTEGER NOT NULL CHECK (paused_seconds >= 0),
    failed_attempts             INTEGER NOT NULL CHECK (failed_attempts >= 0),
    hints_by_tier               JSONB NOT NULL,
    assisted_solve_count        SMALLINT NOT NULL DEFAULT 0 CHECK (assisted_solve_count >= 0),
    optional_solved_count       SMALLINT NOT NULL DEFAULT 0 CHECK (optional_solved_count >= 0),
    grade                       TEXT NOT NULL CHECK (grade IN ('S', 'A', 'B', 'C', 'ASSISTED')),
    rng_seed_reveal             TEXT NOT NULL,
    verification_payload        JSONB NOT NULL,
    deterministic_recap        JSONB NOT NULL,
    ai_recap                    JSONB,
    completed_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(hints_by_tier) = 'object'),
    CHECK (jsonb_typeof(verification_payload) = 'object'),
    CHECK (jsonb_typeof(deterministic_recap) = 'object'),
    CHECK (ai_recap IS NULL OR jsonb_typeof(ai_recap) = 'object')
);

-- Start transaction locks escape_sessions and verifies exactly three users, seats
-- {0,1,2}, one distinct role each, private delivery readiness, a linted graph and
-- generated instances whose solution oracles all pass uniqueness tests.
--
-- Answer transaction reserves Idempotency-Key, locks session+puzzle, checks revision,
-- capability/rate/visibility, decrypts only that puzzle's answer spec, runs the strict
-- validator, applies effects/graph availability and appends audience-filtered events.
-- Commit happens before WebSocket publication or AI flavor generation.
--
-- Item combinations reserve all input rows with SELECT FOR UPDATE in deterministic ID
-- order. A failed recipe releases every reservation. Simultaneous inputs expire as a
-- window and never consume items or partial puzzle state.
--
-- Commitments use SHA-256(random 256-bit salt || canonical payload); the salt remains
-- encrypted until the reveal policy permits it. AES-GCM keys live outside PostgreSQL
-- and never enter logs, analytics, client payloads or LLM prompts.

RESET search_path;
