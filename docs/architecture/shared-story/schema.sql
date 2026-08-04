-- Shared Story / Three Paths, One Fate — PostgreSQL 15+
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS shared_story;
SET search_path TO shared_story, public;

CREATE TABLE story_sessions (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    server_id                   BIGINT NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    channel_id                  BIGINT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    host_user_id                BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    rules_version               TEXT NOT NULL DEFAULT 'three-paths-v1',
    content_version             TEXT NOT NULL,
    status                      TEXT NOT NULL DEFAULT 'LOBBY'
                                CHECK (status IN ('LOBBY', 'CHARACTER_SETUP', 'ACTIVE', 'ENDING', 'COMPLETED', 'PAUSED', 'CANCELLED')),
    revision                    BIGINT NOT NULL DEFAULT 0 CHECK (revision >= 0),
    current_chapter_id          UUID,
    current_scene_id            UUID,
    theme_key                   TEXT,
    tone_profile                JSONB NOT NULL DEFAULT '{}'::jsonb,
    safety_envelope             JSONB NOT NULL DEFAULT '{}'::jsonb,
    session_settings            JSONB NOT NULL DEFAULT '{}'::jsonb,
    public_state                JSONB NOT NULL DEFAULT '{}'::jsonb,
    engine_state_ciphertext     BYTEA,
    encryption_key_version      SMALLINT NOT NULL DEFAULT 1,
    seed_commitment             TEXT,
    rng_seed_ciphertext         BYTEA,
    rng_counter                 BIGINT NOT NULL DEFAULT 0 CHECK (rng_counter >= 0),
    invite_code_hash            BYTEA,
    invite_expires_at           TIMESTAMPTZ,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at                  TIMESTAMPTZ,
    paused_at                   TIMESTAMPTZ,
    completed_at                TIMESTAMPTZ,
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(tone_profile) = 'object'),
    CHECK (jsonb_typeof(safety_envelope) = 'object'),
    CHECK (jsonb_typeof(session_settings) = 'object'),
    CHECK (jsonb_typeof(public_state) = 'object'),
    CHECK ((invite_code_hash IS NULL) = (invite_expires_at IS NULL))
);

CREATE INDEX ix_story_sessions_server_status ON story_sessions (server_id, status, updated_at DESC);

CREATE TABLE story_players (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id                    UUID NOT NULL REFERENCES story_sessions(id) ON DELETE CASCADE,
    user_id                     BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    seat                        SMALLINT NOT NULL CHECK (seat BETWEEN 0 AND 2),
    ready                       BOOLEAN NOT NULL DEFAULT FALSE,
    connection_status           TEXT NOT NULL DEFAULT 'OFFLINE'
                                CHECK (connection_status IN ('ONLINE', 'OFFLINE', 'LEFT')),
    spotlight_tokens            SMALLINT NOT NULL DEFAULT 2 CHECK (spotlight_tokens BETWEEN 0 AND 2),
    assist_tokens               SMALLINT NOT NULL DEFAULT 1 CHECK (assist_tokens BETWEEN 0 AND 1),
    safety_preferences_ciphertext BYTEA NOT NULL,
    encryption_key_version      SMALLINT NOT NULL,
    joined_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at                TIMESTAMPTZ,
    disconnected_at             TIMESTAMPTZ,
    left_at                     TIMESTAMPTZ,
    UNIQUE (story_id, user_id),
    UNIQUE (story_id, seat)
);

CREATE TABLE story_locations (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id                    UUID NOT NULL REFERENCES story_sessions(id) ON DELETE CASCADE,
    location_key                TEXT NOT NULL,
    display_name                TEXT NOT NULL,
    description                 TEXT NOT NULL,
    connected_location_ids      JSONB NOT NULL DEFAULT '[]'::jsonb,
    discovered                  BOOLEAN NOT NULL DEFAULT FALSE,
    accessible                  BOOLEAN NOT NULL DEFAULT TRUE,
    tags                        JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (story_id, location_key),
    CHECK (jsonb_typeof(connected_location_ids) = 'array'),
    CHECK (jsonb_typeof(tags) = 'array')
);

CREATE TABLE characters (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id                    UUID NOT NULL REFERENCES story_sessions(id) ON DELETE CASCADE,
    player_id                   UUID NOT NULL UNIQUE REFERENCES story_players(id) ON DELETE CASCADE,
    name                        TEXT NOT NULL,
    archetype_key               TEXT NOT NULL,
    pronouns                    TEXT NOT NULL,
    current_location_id         UUID NOT NULL REFERENCES story_locations(id) ON DELETE RESTRICT,
    condition                   TEXT NOT NULL DEFAULT 'READY'
                                CHECK (condition IN ('READY', 'STRAINED', 'INJURED', 'EXHAUSTED')),
    public_summary              TEXT NOT NULL DEFAULT '',
    private_summary_ciphertext  BYTEA,
    creation_choices            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(creation_choices) = 'object')
);

CREATE TABLE chapters (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id                    UUID NOT NULL REFERENCES story_sessions(id) ON DELETE CASCADE,
    chapter_number              SMALLINT NOT NULL CHECK (chapter_number BETWEEN 1 AND 5),
    title                       TEXT NOT NULL,
    objective                   TEXT NOT NULL,
    status                      TEXT NOT NULL DEFAULT 'PLANNED'
                                CHECK (status IN ('PLANNED', 'ACTIVE', 'COMPLETED')),
    progress                    JSONB NOT NULL DEFAULT '{}'::jsonb,
    opening_state_revision      BIGINT NOT NULL,
    closing_state_revision      BIGINT,
    started_at                  TIMESTAMPTZ,
    completed_at                TIMESTAMPTZ,
    UNIQUE (story_id, chapter_number),
    CHECK (jsonb_typeof(progress) = 'object')
);

CREATE TABLE scenes (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id                    UUID NOT NULL REFERENCES story_sessions(id) ON DELETE CASCADE,
    chapter_id                  UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    sequence_number             SMALLINT NOT NULL CHECK (sequence_number > 0),
    scene_kind                  TEXT NOT NULL
                                CHECK (scene_kind IN ('OPENING', 'SPOTLIGHT', 'JOINT_DECISION', 'INTERLUDE', 'FINALE', 'EPILOGUE')),
    status                      TEXT NOT NULL DEFAULT 'PLANNED'
                                CHECK (status IN ('PLANNED', 'ACTIVE', 'RESOLVING', 'COMPLETED', 'REPLACED_FOR_SAFETY')),
    location_id                 UUID NOT NULL REFERENCES story_locations(id) ON DELETE RESTRICT,
    spotlight_player_id         UUID REFERENCES story_players(id) ON DELETE RESTRICT,
    participating_character_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    objective                   TEXT NOT NULL,
    state_before_revision       BIGINT NOT NULL,
    state_after_revision        BIGINT,
    started_at                  TIMESTAMPTZ,
    deadline_at                 TIMESTAMPTZ,
    completed_at                TIMESTAMPTZ,
    UNIQUE (story_id, sequence_number),
    CHECK (jsonb_typeof(participating_character_ids) = 'array')
);

ALTER TABLE story_sessions
    ADD CONSTRAINT fk_story_sessions_current_chapter
    FOREIGN KEY (current_chapter_id) REFERENCES chapters(id) ON DELETE SET NULL,
    ADD CONSTRAINT fk_story_sessions_current_scene
    FOREIGN KEY (current_scene_id) REFERENCES scenes(id) ON DELETE SET NULL;

CREATE TABLE world_facts (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id                    UUID NOT NULL REFERENCES story_sessions(id) ON DELETE CASCADE,
    fact_key                    TEXT NOT NULL,
    status                      TEXT NOT NULL CHECK (status IN ('TRUE', 'FALSE', 'UNKNOWN', 'DISPUTED', 'RETIRED')),
    visibility                  TEXT NOT NULL,
    public_value                JSONB,
    private_value_ciphertext    BYTEA,
    source_scene_id             UUID NOT NULL REFERENCES scenes(id) ON DELETE RESTRICT,
    established_revision        BIGINT NOT NULL,
    immutable                   BOOLEAN NOT NULL DEFAULT FALSE,
    tags                        JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (story_id, fact_key),
    CHECK (public_value IS NULL OR jsonb_typeof(public_value) IN ('string', 'number', 'boolean', 'array', 'object', 'null')),
    CHECK (jsonb_typeof(tags) = 'array'),
    CHECK ((visibility = 'PUBLIC' AND public_value IS NOT NULL AND private_value_ciphertext IS NULL)
        OR (visibility <> 'PUBLIC' AND public_value IS NULL AND private_value_ciphertext IS NOT NULL))
);

CREATE TABLE character_facts (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id                    UUID NOT NULL REFERENCES story_sessions(id) ON DELETE CASCADE,
    character_id                UUID NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    fact_key                    TEXT NOT NULL,
    visibility                  TEXT NOT NULL,
    public_value                JSONB,
    private_value_ciphertext    BYTEA,
    source_scene_id             UUID NOT NULL REFERENCES scenes(id) ON DELETE RESTRICT,
    tags                        JSONB NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE (character_id, fact_key),
    CHECK (jsonb_typeof(tags) = 'array'),
    CHECK ((visibility = 'PUBLIC' AND public_value IS NOT NULL AND private_value_ciphertext IS NULL)
        OR (visibility <> 'PUBLIC' AND public_value IS NULL AND private_value_ciphertext IS NOT NULL))
);

CREATE TABLE story_goals (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id                    UUID NOT NULL REFERENCES story_sessions(id) ON DELETE CASCADE,
    goal_key                    TEXT NOT NULL,
    title                       TEXT NOT NULL,
    description                 TEXT NOT NULL,
    owner_type                  TEXT NOT NULL CHECK (owner_type IN ('PARTY', 'CHARACTER')),
    owner_character_id          UUID REFERENCES characters(id) ON DELETE CASCADE,
    visibility                  TEXT NOT NULL,
    status                      TEXT NOT NULL DEFAULT 'ACTIVE'
                                CHECK (status IN ('ACTIVE', 'COMPLETED', 'FAILED_FORWARD', 'ABANDONED')),
    progress                    SMALLINT NOT NULL DEFAULT 0 CHECK (progress >= 0),
    target                      SMALLINT NOT NULL CHECK (target > 0),
    effect_spec                 JSONB NOT NULL,
    created_in_scene_id         UUID NOT NULL REFERENCES scenes(id) ON DELETE RESTRICT,
    resolved_in_scene_id        UUID REFERENCES scenes(id) ON DELETE RESTRICT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (story_id, goal_key),
    CHECK (jsonb_typeof(effect_spec) = 'object'),
    CHECK ((owner_type = 'PARTY' AND owner_character_id IS NULL)
        OR (owner_type = 'CHARACTER' AND owner_character_id IS NOT NULL))
);

CREATE TABLE story_mysteries (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id                    UUID NOT NULL REFERENCES story_sessions(id) ON DELETE CASCADE,
    mystery_key                 TEXT NOT NULL,
    question                    TEXT NOT NULL,
    status                      TEXT NOT NULL DEFAULT 'OPEN'
                                CHECK (status IN ('OPEN', 'PARTIALLY_RESOLVED', 'RESOLVED', 'LEFT_AMBIGUOUS')),
    progress                    SMALLINT NOT NULL DEFAULT 0 CHECK (progress >= 0),
    target                      SMALLINT NOT NULL CHECK (target > 0),
    visibility                  TEXT NOT NULL,
    known_clue_fact_ids         JSONB NOT NULL DEFAULT '[]'::jsonb,
    solution_payload_ciphertext BYTEA NOT NULL,
    payoff_chapter              SMALLINT NOT NULL CHECK (payoff_chapter BETWEEN 1 AND 5),
    UNIQUE (story_id, mystery_key),
    CHECK (jsonb_typeof(known_clue_fact_ids) = 'array')
);

CREATE TABLE inventory_items (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id                    UUID NOT NULL REFERENCES story_sessions(id) ON DELETE CASCADE,
    definition_key              TEXT NOT NULL,
    owner_character_id          UUID REFERENCES characters(id) ON DELETE CASCADE,
    location_id                 UUID REFERENCES story_locations(id) ON DELETE SET NULL,
    display_name                TEXT NOT NULL,
    quantity                    SMALLINT NOT NULL DEFAULT 1 CHECK (quantity BETWEEN 0 AND 20),
    durability                  SMALLINT CHECK (durability BETWEEN 0 AND 10),
    visibility                  TEXT NOT NULL,
    tags                        JSONB NOT NULL DEFAULT '[]'::jsonb,
    acquired_in_scene_id        UUID NOT NULL REFERENCES scenes(id) ON DELETE RESTRICT,
    removed_in_scene_id         UUID REFERENCES scenes(id) ON DELETE RESTRICT,
    CHECK (jsonb_typeof(tags) = 'array'),
    CHECK (owner_character_id IS NOT NULL OR location_id IS NOT NULL)
);

CREATE INDEX ix_inventory_items_owner ON inventory_items (owner_character_id) WHERE quantity > 0;

CREATE TABLE relationship_states (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id                    UUID NOT NULL REFERENCES story_sessions(id) ON DELETE CASCADE,
    from_character_id           UUID NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    to_character_id             UUID NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    trust                       SMALLINT NOT NULL DEFAULT 0 CHECK (trust BETWEEN -5 AND 5),
    affection                   SMALLINT NOT NULL DEFAULT 0 CHECK (affection BETWEEN -5 AND 5),
    tension                     SMALLINT NOT NULL DEFAULT 0 CHECK (tension BETWEEN 0 AND 5),
    obligations                 JSONB NOT NULL DEFAULT '[]'::jsonb,
    public_summary              TEXT NOT NULL DEFAULT '',
    last_changed_scene_id       UUID NOT NULL REFERENCES scenes(id) ON DELETE RESTRICT,
    UNIQUE (story_id, from_character_id, to_character_id),
    CHECK (from_character_id <> to_character_id),
    CHECK (jsonb_typeof(obligations) = 'array')
);

CREATE TABLE secrets (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id                    UUID NOT NULL REFERENCES story_sessions(id) ON DELETE CASCADE,
    owner_player_id             UUID REFERENCES story_players(id) ON DELETE CASCADE,
    owner_character_id          UUID REFERENCES characters(id) ON DELETE CASCADE,
    title_ciphertext            BYTEA NOT NULL,
    payload_ciphertext          BYTEA NOT NULL,
    payload_commitment          TEXT NOT NULL,
    permitted_audience          JSONB NOT NULL,
    reveal_conditions           JSONB NOT NULL,
    revealed                    BOOLEAN NOT NULL DEFAULT FALSE,
    revealed_payload            JSONB,
    created_in_chapter_id       UUID NOT NULL REFERENCES chapters(id) ON DELETE RESTRICT,
    revealed_in_scene_id        UUID REFERENCES scenes(id) ON DELETE RESTRICT,
    encryption_key_version      SMALLINT NOT NULL,
    CHECK (owner_player_id IS NOT NULL OR owner_character_id IS NOT NULL),
    CHECK (jsonb_typeof(permitted_audience) = 'array'),
    CHECK (jsonb_typeof(reveal_conditions) = 'array'),
    CHECK (revealed_payload IS NULL OR jsonb_typeof(revealed_payload) = 'object'),
    CHECK (revealed = (revealed_payload IS NOT NULL))
);

CREATE TABLE narrative_promises (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id                    UUID NOT NULL REFERENCES story_sessions(id) ON DELETE CASCADE,
    setup_text                  TEXT,
    setup_ciphertext            BYTEA,
    visibility                  TEXT NOT NULL,
    payoff_type                 TEXT NOT NULL CHECK (payoff_type IN ('MYSTERY', 'RELATIONSHIP', 'ITEM', 'THREAT', 'CHARACTER_ARC')),
    promise_slot                SMALLINT NOT NULL CHECK (promise_slot BETWEEN 1 AND 6),
    status                      TEXT NOT NULL DEFAULT 'OPEN'
                                CHECK (status IN ('OPEN', 'FULFILLED', 'SUBVERTED', 'EXPIRED_WITH_CALLBACK')),
    priority                    SMALLINT NOT NULL CHECK (priority BETWEEN 1 AND 3),
    established_in_scene_id     UUID NOT NULL REFERENCES scenes(id) ON DELETE RESTRICT,
    due_by_chapter              SMALLINT NOT NULL CHECK (due_by_chapter BETWEEN 1 AND 5),
    payoff_scene_id             UUID REFERENCES scenes(id) ON DELETE RESTRICT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((visibility = 'PUBLIC' AND setup_text IS NOT NULL AND setup_ciphertext IS NULL)
        OR (visibility <> 'PUBLIC' AND setup_text IS NULL AND setup_ciphertext IS NOT NULL))
);

CREATE UNIQUE INDEX uq_open_narrative_promise_slots
    ON narrative_promises (story_id, promise_slot) WHERE status = 'OPEN';

CREATE TABLE player_actions (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id                    UUID NOT NULL REFERENCES story_sessions(id) ON DELETE CASCADE,
    scene_id                    UUID NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    player_id                   UUID NOT NULL REFERENCES story_players(id) ON DELETE RESTRICT,
    character_id                UUID NOT NULL REFERENCES characters(id) ON DELETE RESTRICT,
    idempotency_key             TEXT NOT NULL,
    action_kind                 TEXT NOT NULL
                                CHECK (action_kind IN ('INVESTIGATE', 'MOVE', 'TALK', 'USE_ITEM', 'ASSIST_PLAYER', 'DECEIVE', 'REVEAL_SECRET', 'REST', 'VOTE', 'ATTEMPT_RISKY_ACTION')),
    visibility                  TEXT NOT NULL,
    public_input                JSONB,
    private_input_ciphertext    BYTEA,
    interpreted_action          JSONB NOT NULL,
    outcome                     TEXT CHECK (outcome IN ('SUCCESS', 'SUCCESS_WITH_COST', 'FAIL_FORWARD')),
    expected_revision           BIGINT NOT NULL,
    applied_revision            BIGINT,
    status                      TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPLIED', 'REJECTED')),
    rejection_code              TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at                 TIMESTAMPTZ,
    UNIQUE (story_id, player_id, idempotency_key),
    CHECK (jsonb_typeof(interpreted_action) = 'object'),
    CHECK (public_input IS NULL OR jsonb_typeof(public_input) = 'object'),
    CHECK ((visibility = 'PUBLIC' AND public_input IS NOT NULL AND private_input_ciphertext IS NULL)
        OR (visibility <> 'PUBLIC' AND public_input IS NULL AND private_input_ciphertext IS NOT NULL))
);

CREATE INDEX ix_player_actions_scene ON player_actions (story_id, scene_id, created_at);

CREATE TABLE story_choices (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id                    UUID NOT NULL REFERENCES story_sessions(id) ON DELETE CASCADE,
    scene_id                    UUID NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    definition_key              TEXT NOT NULL,
    label                       TEXT NOT NULL,
    description                 TEXT NOT NULL,
    action_kind                 TEXT NOT NULL,
    effect_envelope             JSONB NOT NULL,
    preconditions               JSONB NOT NULL DEFAULT '[]'::jsonb,
    visibility                  TEXT NOT NULL DEFAULT 'PUBLIC',
    reveal_policy               TEXT NOT NULL DEFAULT 'AFTER_RESOLUTION'
                                CHECK (reveal_policy IN ('AFTER_RESOLUTION', 'AT_ENDING', 'NEVER')),
    eligible_player_ids         JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (scene_id, definition_key),
    CHECK (jsonb_typeof(effect_envelope) = 'object'),
    CHECK (jsonb_typeof(preconditions) = 'array'),
    CHECK (jsonb_typeof(eligible_player_ids) = 'array')
);

CREATE TABLE story_choice_votes (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id                    UUID NOT NULL REFERENCES story_sessions(id) ON DELETE CASCADE,
    scene_id                    UUID NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    player_id                   UUID NOT NULL REFERENCES story_players(id) ON DELETE CASCADE,
    choice_id_ciphertext        BYTEA NOT NULL,
    choice_commitment           TEXT NOT NULL,
    revealed_choice_id          UUID REFERENCES story_choices(id) ON DELETE CASCADE,
    encryption_key_version      SMALLINT NOT NULL,
    idempotency_key             TEXT NOT NULL,
    submitted_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    revealed_at                 TIMESTAMPTZ,
    UNIQUE (scene_id, player_id),
    UNIQUE (story_id, player_id, idempotency_key),
    CHECK ((revealed_choice_id IS NULL) = (revealed_at IS NULL))
);

-- choice_commitment = SHA-256(random 256-bit salt || canonical choice id). The salt
-- stays inside choice_id_ciphertext until the reveal policy permits publication;
-- otherwise a two/three-choice commitment could be brute-forced during voting.

CREATE TABLE chapter_summaries (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id                    UUID NOT NULL REFERENCES story_sessions(id) ON DELETE CASCADE,
    chapter_id                  UUID NOT NULL UNIQUE REFERENCES chapters(id) ON DELETE CASCADE,
    state_revision              BIGINT NOT NULL,
    canonical_summary           JSONB NOT NULL,
    public_summary              TEXT NOT NULL,
    private_addenda_ciphertext  BYTEA,
    token_count                 INTEGER NOT NULL CHECK (token_count >= 0),
    model_profile               TEXT,
    prompt_version              TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(canonical_summary) = 'object')
);

CREATE TABLE story_state_snapshots (
    id                          BIGSERIAL PRIMARY KEY,
    story_id                    UUID NOT NULL REFERENCES story_sessions(id) ON DELETE CASCADE,
    revision                    BIGINT NOT NULL,
    public_state                JSONB NOT NULL,
    private_state_ciphertext    BYTEA NOT NULL,
    rng_counter                 BIGINT NOT NULL,
    reason                      TEXT NOT NULL CHECK (reason IN ('ACTION', 'SCENE_END', 'CHAPTER_END', 'PAUSE', 'ENDING')),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (story_id, revision),
    CHECK (jsonb_typeof(public_state) = 'object')
);

-- One table for scene prose, choices, summaries, private passages and endings.
CREATE TABLE generated_story_content (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id                    UUID NOT NULL REFERENCES story_sessions(id) ON DELETE CASCADE,
    chapter_id                  UUID REFERENCES chapters(id) ON DELETE CASCADE,
    scene_id                    UUID REFERENCES scenes(id) ON DELETE CASCADE,
    audience                    TEXT NOT NULL,
    content_kind                TEXT NOT NULL
                                CHECK (content_kind IN ('DIRECTOR_PLAN', 'SCENE_PROSE', 'PRIVATE_PASSAGE', 'ACTION_INTERPRETATION', 'CHOICES', 'CONTINUITY_REPORT', 'CHAPTER_SUMMARY', 'ENDING', 'EPILOGUE')),
    status                      TEXT NOT NULL DEFAULT 'PENDING'
                                CHECK (status IN ('PENDING', 'PROCESSING', 'READY', 'REJECTED', 'FALLBACK')),
    source_revision             BIGINT NOT NULL,
    input_fingerprint           TEXT NOT NULL,
    output_public               JSONB,
    output_private_ciphertext   BYTEA,
    lore_reference_ids          JSONB NOT NULL DEFAULT '[]'::jsonb,
    model_profile               TEXT NOT NULL,
    model_name                  TEXT,
    prompt_version              TEXT NOT NULL,
    attempts                    SMALLINT NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 3),
    lease_owner                 TEXT,
    lease_expires_at            TIMESTAMPTZ,
    error_code                  TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at                TIMESTAMPTZ,
    UNIQUE (story_id, content_kind, audience, input_fingerprint),
    CHECK (output_public IS NULL OR jsonb_typeof(output_public) = 'object'),
    CHECK (jsonb_typeof(lore_reference_ids) = 'array'),
    CHECK ((audience = 'PUBLIC' AND output_private_ciphertext IS NULL)
        OR (audience <> 'PUBLIC' AND output_public IS NULL))
);

CREATE INDEX ix_generated_story_content_claim
    ON generated_story_content (status, lease_expires_at, created_at)
    WHERE status IN ('PENDING', 'PROCESSING');

-- Start transaction locks story_sessions and verifies exactly three distinct users,
-- seats {0,1,2}, one character each, ready state and compatible safety envelope.
--
-- Action transaction reserves Idempotency-Key, locks story_sessions, validates the
-- action capability/revision/visibility, runs the pure reducer, writes a snapshot,
-- advances revision and commits before any narration job or WebSocket broadcast.
-- Save is automatic at every committed action; explicit pause adds a PAUSE snapshot.
-- Resume never rolls back shared history. Fork/rewind is intentionally postponed.
--
-- Private values and player hard lines use application-level AES-256-GCM with
-- associated data binding table/story/player/record IDs. Keys never enter PostgreSQL,
-- centralized logs, analytics or LLM traces.

RESET search_path;
