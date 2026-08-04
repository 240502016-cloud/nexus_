-- AI Commentator reference schema for PostgreSQL 16.
-- Design artifact only: implementation should use SQLAlchemy + Alembic.
-- `players` is the shared Party Lore player projection. The compatible definition is repeated
-- with IF NOT EXISTS so this document can be understood independently.

CREATE TABLE IF NOT EXISTS players (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    server_id           bigint NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    user_id             bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    display_name        varchar(64) NOT NULL,
    is_active           boolean NOT NULL DEFAULT true,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (server_id, user_id)
);

CREATE TABLE commentator_profiles (
    id                  uuid PRIMARY KEY,
    server_id           bigint REFERENCES servers(id) ON DELETE CASCADE,
    profile_key         varchar(64) NOT NULL,
    name                varchar(80) NOT NULL,
    description         varchar(240) NOT NULL,
    system_rules        jsonb NOT NULL,
    sentence_max_chars  smallint NOT NULL DEFAULT 180,
    harshness           smallint NOT NULL DEFAULT 1,
    lore_usage_probability real NOT NULL DEFAULT 0.25,
    is_builtin          boolean NOT NULL DEFAULT false,
    is_enabled          boolean NOT NULL DEFAULT true,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (sentence_max_chars BETWEEN 40 AND 240),
    CHECK (harshness BETWEEN 0 AND 3),
    CHECK (lore_usage_probability BETWEEN 0 AND 1),
    UNIQUE NULLS NOT DISTINCT (server_id, profile_key)
);

CREATE TABLE player_preferences (
    player_id           bigint PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
    commentary_enabled  boolean NOT NULL DEFAULT true,
    allow_targeted_jokes boolean NOT NULL DEFAULT true,
    allow_lore_references boolean NOT NULL DEFAULT true,
    maximum_harshness   smallint NOT NULL DEFAULT 1,
    preferred_humor_styles text[] NOT NULL DEFAULT ARRAY['GENTLE']::text[],
    blocked_topics      text[] NOT NULL DEFAULT '{}',
    tts_enabled         boolean NOT NULL DEFAULT true,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (maximum_harshness BETWEEN 0 AND 3)
);

CREATE TABLE commentary_sessions (
    id                  uuid PRIMARY KEY,
    server_id           bigint NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    game_key            varchar(80) NOT NULL,
    external_match_id   varchar(160),
    profile_id          uuid NOT NULL REFERENCES commentator_profiles(id) ON DELETE RESTRICT,
    started_by_player_id bigint NOT NULL REFERENCES players(id) ON DELETE RESTRICT,
    output_channel_id   bigint REFERENCES channels(id) ON DELETE SET NULL,
    status              varchar(16) NOT NULL DEFAULT 'ACTIVE',
    intensity           varchar(16) NOT NULL DEFAULT 'NORMAL',
    silent_mode         boolean NOT NULL DEFAULT false,
    tts_enabled         boolean NOT NULL DEFAULT false,
    current_tone        varchar(16) NOT NULL DEFAULT 'UNKNOWN',
    event_count         integer NOT NULL DEFAULT 0,
    commentary_count    integer NOT NULL DEFAULT 0,
    started_at          timestamptz NOT NULL DEFAULT now(),
    ended_at            timestamptz,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (status IN ('ACTIVE', 'ENDING', 'ENDED')),
    CHECK (intensity IN ('LOW', 'NORMAL', 'HIGH')),
    CHECK (current_tone IN ('CALM', 'FOCUSED', 'PLAYFUL', 'TENSE', 'UPSET', 'UNKNOWN')),
    CHECK (event_count >= 0 AND commentary_count >= 0),
    CHECK ((status <> 'ENDED') OR ended_at IS NOT NULL)
);

CREATE UNIQUE INDEX uq_commentary_active_game
    ON commentary_sessions (server_id, game_key)
    WHERE status = 'ACTIVE';

CREATE TABLE commentary_session_players (
    session_id          uuid NOT NULL REFERENCES commentary_sessions(id) ON DELETE CASCADE,
    player_id           bigint NOT NULL REFERENCES players(id) ON DELETE RESTRICT,
    is_present          boolean NOT NULL DEFAULT true,
    joined_at           timestamptz NOT NULL DEFAULT now(),
    left_at             timestamptz,
    preference_snapshot jsonb NOT NULL,
    targeted_count      integer NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, player_id),
    CHECK (targeted_count >= 0)
);

CREATE TABLE session_events (
    id                  uuid PRIMARY KEY,
    session_id          uuid NOT NULL REFERENCES commentary_sessions(id) ON DELETE CASCADE,
    external_event_id   varchar(160) NOT NULL,
    source              varchar(24) NOT NULL,
    category            varchar(32) NOT NULL,
    occurred_at         timestamptz NOT NULL,
    received_at         timestamptz NOT NULL DEFAULT now(),
    actor_player_ids    bigint[] NOT NULL DEFAULT '{}',
    target_player_ids   bigint[] NOT NULL DEFAULT '{}',
    normalized_summary  varchar(240) NOT NULL,
    game_context        jsonb NOT NULL DEFAULT '{}'::jsonb,
    normalized_attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    importance          real NOT NULL,
    source_confidence   real NOT NULL,
    novelty_score       real NOT NULL DEFAULT 0.5,
    trigger_score       real,
    trigger_decision    varchar(24),
    deduplication_key   char(64) NOT NULL,
    processing_state    varchar(24) NOT NULL DEFAULT 'PENDING',
    lease_owner         varchar(100),
    lease_expires_at    timestamptz,
    processed_at        timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (source IN ('MANUAL', 'DISCORD', 'GAME_CONNECTOR', 'TRANSCRIPT')),
    CHECK (category IN ('PLAYER_DEATH', 'PLAYER_FAIL', 'CLUTCH', 'BETRAYAL', 'TEAMWORK',
        'ACCIDENTAL_SUCCESS', 'REPEATED_MISTAKE', 'SILENCE', 'ARGUMENT', 'MILESTONE', 'MANUAL_NOTE')),
    CHECK (importance BETWEEN 0 AND 1),
    CHECK (source_confidence BETWEEN 0 AND 1),
    CHECK (novelty_score BETWEEN 0 AND 1),
    CHECK (trigger_score IS NULL OR trigger_score BETWEEN 0 AND 1),
    CHECK (trigger_decision IS NULL OR trigger_decision IN ('SILENT_MODE', 'BELOW_THRESHOLD',
        'COOLDOWN', 'FAIRNESS', 'SAFETY', 'GENERATE', 'SUPERSEDED', 'STALE')),
    CHECK (processing_state IN ('PENDING', 'CLAIMED', 'PROCESSED', 'DROPPED', 'FAILED')),
    UNIQUE (session_id, external_event_id)
);

CREATE INDEX ix_session_events_worker
    ON session_events (processing_state, received_at)
    WHERE processing_state IN ('PENDING', 'CLAIMED');
CREATE INDEX ix_session_events_recent
    ON session_events (session_id, occurred_at DESC);
CREATE INDEX ix_session_events_dedup
    ON session_events (session_id, deduplication_key, occurred_at DESC);

CREATE TABLE generated_commentary (
    id                  uuid PRIMARY KEY,
    session_id          uuid NOT NULL REFERENCES commentary_sessions(id) ON DELETE CASCADE,
    primary_event_id    uuid REFERENCES session_events(id) ON DELETE SET NULL,
    source_event_ids    uuid[] NOT NULL,
    profile_id          uuid NOT NULL REFERENCES commentator_profiles(id) ON DELETE RESTRICT,
    should_comment      boolean NOT NULL,
    commentary_text     varchar(240),
    target_player_id    bigint REFERENCES players(id) ON DELETE SET NULL,
    tone                varchar(16),
    confidence          real NOT NULL,
    reason_code         varchar(32) NOT NULL,
    model_profile       varchar(80) NOT NULL,
    provider_model      varchar(160),
    prompt_version      varchar(40) NOT NULL,
    input_tokens        integer,
    output_tokens       integer,
    latency_ms          integer,
    phrase_hash         char(64),
    dispatch_state      varchar(24) NOT NULL DEFAULT 'PENDING',
    dispatch_error_code varchar(64),
    delivered_at        timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    CHECK ((should_comment AND commentary_text IS NOT NULL) OR
           (NOT should_comment AND commentary_text IS NULL)),
    CHECK (tone IS NULL OR tone IN ('PLAYFUL', 'DRY', 'HYPE', 'ANALYTICAL', 'GENTLE', 'DRAMATIC')),
    CHECK (confidence BETWEEN 0 AND 1),
    CHECK (reason_code IN ('NOTABLE_EVENT', 'REPEATED_MISTAKE', 'LORE_CALLBACK', 'MILESTONE',
        'TEAM_MOMENT', 'SAFETY_VETO', 'TOO_REPETITIVE', 'INSUFFICIENT_CONTEXT')),
    CHECK (dispatch_state IN ('PENDING', 'DELIVERED', 'SUPPRESSED', 'FAILED', 'STALE')),
    CHECK (latency_ms IS NULL OR latency_ms >= 0),
    CHECK (input_tokens IS NULL OR input_tokens >= 0),
    CHECK (output_tokens IS NULL OR output_tokens >= 0)
);

CREATE INDEX ix_generated_commentary_history
    ON generated_commentary (session_id, created_at DESC);
CREATE INDEX ix_generated_commentary_target
    ON generated_commentary (session_id, target_player_id, created_at DESC);
CREATE INDEX ix_generated_commentary_phrase
    ON generated_commentary (session_id, phrase_hash, created_at DESC)
    WHERE phrase_hash IS NOT NULL;

CREATE TABLE commentary_feedback (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    commentary_id       uuid NOT NULL REFERENCES generated_commentary(id) ON DELETE CASCADE,
    player_id           bigint NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    feedback_type       varchar(24) NOT NULL,
    details             varchar(500),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (feedback_type IN ('FUNNY', 'NOT_FUNNY', 'TOO_HARSH', 'REPETITIVE', 'WRONG_CONTEXT')),
    UNIQUE (commentary_id, player_id)
);

CREATE TABLE cooldown_state (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id          uuid NOT NULL REFERENCES commentary_sessions(id) ON DELETE CASCADE,
    scope_type          varchar(20) NOT NULL,
    scope_key           varchar(160) NOT NULL,
    last_used_at        timestamptz NOT NULL,
    cooldown_until      timestamptz NOT NULL,
    usage_count         integer NOT NULL DEFAULT 1,
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (scope_type IN ('GLOBAL', 'PLAYER', 'CATEGORY', 'PHRASE', 'LORE', 'PERSONALITY_PATTERN')),
    CHECK (usage_count >= 1),
    UNIQUE (session_id, scope_type, scope_key)
);

CREATE INDEX ix_cooldown_active
    ON cooldown_state (session_id, cooldown_until DESC);

-- `lore_entries` is added by Party Lore. Add this table only in Phase 3 when that migration exists.
CREATE TABLE lore_references (
    commentary_id       uuid NOT NULL REFERENCES generated_commentary(id) ON DELETE CASCADE,
    lore_id             bigint NOT NULL REFERENCES lore_entries(id) ON DELETE RESTRICT,
    relevance_score     real NOT NULL,
    actually_used       boolean NOT NULL DEFAULT false,
    created_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (commentary_id, lore_id),
    CHECK (relevance_score BETWEEN 0 AND 1)
);

CREATE INDEX ix_lore_references_reverse
    ON lore_references (lore_id, created_at DESC);

-- Service invariants that accompany the DDL:
-- 1. Every session has exactly three distinct active players before it accepts events.
-- 2. Player IDs in event arrays must belong to the same server/session.
-- 3. Built-in profile JSON is code-owned and cannot be edited through public APIs.
-- 4. A generated line is dispatched only if all referenced lore IDs and player policies still pass
--    a second safety check immediately before delivery.
