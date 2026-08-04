-- AI Roast Battle reference schema for PostgreSQL 16.
-- Design artifact only. Production implementation uses SQLAlchemy + Alembic.

CREATE TABLE roast_profiles (
    player_id           bigint PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
    roast_enabled       boolean NOT NULL DEFAULT false,
    maximum_intensity   smallint NOT NULL DEFAULT 1,
    allow_party_lore    boolean NOT NULL DEFAULT false,
    allow_recent_failures boolean NOT NULL DEFAULT false,
    allow_quotes        boolean NOT NULL DEFAULT false,
    allow_match_statistics boolean NOT NULL DEFAULT true,
    allow_highlights    boolean NOT NULL DEFAULT true,
    allow_self_descriptions boolean NOT NULL DEFAULT true,
    allow_mild_profanity boolean NOT NULL DEFAULT false,
    hard_blocked_categories text[] NOT NULL DEFAULT ARRAY[
        'MEDICAL', 'MENTAL_HEALTH', 'APPEARANCE', 'PROTECTED_IDENTITY', 'FAMILY',
        'ROMANTIC_OR_SEXUAL_HISTORY', 'WORK', 'FINANCE', 'TRAUMA', 'REAL_CONFLICT',
        'PRIVATE_MESSAGES', 'SECRETS', 'UNVERIFIED_REAL_LIFE_CLAIMS'
    ]::text[],
    consent_version     integer NOT NULL DEFAULT 1,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (maximum_intensity BETWEEN 0 AND 4),
    CHECK (consent_version >= 1)
);

CREATE TABLE roast_topic_permissions (
    player_id           bigint NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    topic_code          varchar(40) NOT NULL,
    permission_state    varchar(16) NOT NULL DEFAULT 'BLOCKED',
    updated_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (player_id, topic_code),
    CHECK (topic_code IN ('GAMING_MISTAKES', 'FAILED_STRATEGIES', 'HARMLESS_QUOTES',
        'MATCH_STATISTICS', 'FUNNY_HIGHLIGHTS', 'CONFIRMED_PARTY_LORE', 'SELF_DESCRIPTIONS',
        'NAVIGATION', 'TEAMWORK', 'INVENTORY', 'TIMING', 'REACTIONS')),
    CHECK (permission_state IN ('ALLOWED', 'BLOCKED'))
);

CREATE TABLE blocked_topics (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id           bigint NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    block_type          varchar(20) NOT NULL,
    normalized_value    varchar(160) NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (block_type IN ('TOPIC_CODE', 'TAG', 'LORE_ID', 'SOURCE_ID', 'ANGLE')),
    UNIQUE (player_id, block_type, normalized_value)
);

CREATE TABLE roast_sessions (
    id                  uuid PRIMARY KEY,
    server_id           bigint NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    created_by_player_id bigint NOT NULL REFERENCES players(id) ON DELETE RESTRICT,
    mode                varchar(40) NOT NULL,
    requested_intensity smallint NOT NULL DEFAULT 1,
    status              varchar(24) NOT NULL DEFAULT 'CONSENT_PENDING',
    maximum_rounds      smallint NOT NULL DEFAULT 3,
    current_round_number smallint NOT NULL DEFAULT 0,
    recap_status        varchar(16) NOT NULL DEFAULT 'NOT_REQUESTED',
    recap_title         varchar(120),
    recap_summary       text,
    prompt_version      varchar(40),
    created_at          timestamptz NOT NULL DEFAULT now(),
    started_at          timestamptz,
    ended_at            timestamptz,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (mode IN ('BALANCED_SPOTLIGHT', 'TOPIC_CARDS', 'PLAYER_WRITTEN_AI_JUDGE',
        'PLAYER_VS_AI', 'TEAM_ROAST', 'FAKE_AWARDS', 'SESSION_RECAP_GAUNTLET')),
    CHECK (requested_intensity BETWEEN 0 AND 4),
    CHECK (status IN ('CONSENT_PENDING', 'ACTIVE', 'ENDING', 'ENDED', 'CANCELLED')),
    CHECK (maximum_rounds BETWEEN 1 AND 12),
    CHECK (current_round_number BETWEEN 0 AND maximum_rounds),
    CHECK (recap_status IN ('NOT_REQUESTED', 'QUEUED', 'READY', 'FAILED')),
    CHECK ((status NOT IN ('ENDED', 'CANCELLED')) OR ended_at IS NOT NULL)
);

CREATE UNIQUE INDEX uq_roast_active_server
    ON roast_sessions (server_id)
    WHERE status IN ('CONSENT_PENDING', 'ACTIVE', 'ENDING');

CREATE TABLE roast_session_players (
    session_id          uuid NOT NULL REFERENCES roast_sessions(id) ON DELETE CASCADE,
    player_id           bigint NOT NULL REFERENCES players(id) ON DELETE RESTRICT,
    seat_number         smallint NOT NULL,
    consent_state       varchar(16) NOT NULL DEFAULT 'PENDING',
    profile_consent_version integer NOT NULL,
    profile_snapshot    jsonb NOT NULL,
    effective_maximum_intensity smallint NOT NULL,
    target_count        smallint NOT NULL DEFAULT 0,
    total_score         real NOT NULL DEFAULT 0,
    consented_at        timestamptz,
    revoked_at          timestamptz,
    PRIMARY KEY (session_id, player_id),
    CHECK (seat_number BETWEEN 1 AND 3),
    CHECK (consent_state IN ('PENDING', 'READY', 'DECLINED', 'REVOKED')),
    CHECK (profile_consent_version >= 1),
    CHECK (effective_maximum_intensity BETWEEN 0 AND 4),
    CHECK (target_count >= 0),
    UNIQUE (session_id, seat_number)
);

CREATE TABLE roast_rounds (
    id                  uuid PRIMARY KEY,
    session_id          uuid NOT NULL REFERENCES roast_sessions(id) ON DELETE CASCADE,
    round_number        smallint NOT NULL,
    target_player_id    bigint REFERENCES players(id) ON DELETE SET NULL,
    submitted_topic     varchar(40),
    effective_intensity smallint NOT NULL,
    status              varchar(20) NOT NULL DEFAULT 'PENDING',
    fallback_type       varchar(20),
    selected_candidate_id uuid,
    started_at          timestamptz NOT NULL DEFAULT now(),
    voting_started_at   timestamptz,
    completed_at        timestamptz,
    CHECK (round_number >= 1),
    CHECK (effective_intensity BETWEEN 0 AND 4),
    CHECK (status IN ('PENDING', 'GENERATING', 'TARGET_REVIEW', 'VOTING', 'COMPLETED', 'SKIPPED')),
    CHECK (fallback_type IS NULL OR fallback_type IN ('GROUP_GENERIC', 'AI_SELF_ROAST', 'SKIP_ROUND')),
    UNIQUE (session_id, round_number)
);

CREATE TABLE roast_candidates (
    id                  uuid PRIMARY KEY,
    round_id            uuid NOT NULL REFERENCES roast_rounds(id) ON DELETE CASCADE,
    target_player_id    bigint REFERENCES players(id) ON DELETE SET NULL,
    roast_text          varchar(280) NOT NULL,
    roast_text_sha256   char(64) NOT NULL,
    angle               varchar(40) NOT NULL,
    intensity           smallint NOT NULL,
    source_lore_ids     bigint[] NOT NULL DEFAULT '{}',
    risk_flags          text[] NOT NULL DEFAULT '{}',
    repetition_score    real NOT NULL,
    confidence          real NOT NULL,
    quality_score       real NOT NULL,
    structure_fingerprint char(64) NOT NULL,
    safety_state        varchar(20) NOT NULL DEFAULT 'APPROVED',
    status              varchar(20) NOT NULL DEFAULT 'ELIGIBLE',
    model_profile       varchar(80) NOT NULL,
    provider_model      varchar(160),
    prompt_version      varchar(40) NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    displayed_at        timestamptz,
    CHECK (char_length(roast_text) BETWEEN 1 AND 280),
    CHECK (intensity BETWEEN 0 AND 4),
    CHECK (cardinality(source_lore_ids) <= 1),
    CHECK (repetition_score BETWEEN 0 AND 1),
    CHECK (confidence BETWEEN 0 AND 1),
    CHECK (quality_score BETWEEN 0 AND 1),
    CHECK (safety_state IN ('APPROVED', 'TARGET_APPROVED')),
    CHECK (status IN ('ELIGIBLE', 'SELECTED', 'DISPLAYED', 'DISCARDED')),
    UNIQUE (round_id, roast_text_sha256)
);

ALTER TABLE roast_rounds
    ADD CONSTRAINT fk_roast_round_selected_candidate
    FOREIGN KEY (selected_candidate_id) REFERENCES roast_candidates(id) ON DELETE SET NULL;

CREATE INDEX ix_roast_candidates_recent_phrase
    ON roast_candidates (roast_text_sha256, created_at DESC);
CREATE INDEX ix_roast_candidates_target_recent
    ON roast_candidates (target_player_id, displayed_at DESC)
    WHERE status = 'DISPLAYED';

CREATE TABLE roast_votes (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    candidate_id        uuid NOT NULL REFERENCES roast_candidates(id) ON DELETE CASCADE,
    voter_player_id     bigint NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    vote_type           varchar(12) NOT NULL,
    emoji               varchar(8),
    reaction_time_ms    integer,
    is_target_vote      boolean NOT NULL DEFAULT false,
    score_contribution  real NOT NULL DEFAULT 0,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (vote_type IN ('FUNNY', 'OKAY', 'PASS')),
    CHECK (emoji IS NULL OR emoji IN ('😂', '👏', '😐')),
    CHECK (reaction_time_ms IS NULL OR reaction_time_ms BETWEEN 0 AND 120000),
    UNIQUE (candidate_id, voter_player_id)
);

CREATE TABLE roast_feedback (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    candidate_id        uuid NOT NULL REFERENCES roast_candidates(id) ON DELETE CASCADE,
    player_id           bigint NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    feedback_type       varchar(24) NOT NULL,
    details             varchar(500),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (feedback_type IN ('FUNNY', 'TOO_HARSH', 'REPETITIVE', 'WRONG_CONTEXT', 'SKIP_FUTURE')),
    UNIQUE (candidate_id, player_id)
);

CREATE TABLE roast_context_usage (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    candidate_id        uuid NOT NULL REFERENCES roast_candidates(id) ON DELETE CASCADE,
    source_type         varchar(24) NOT NULL,
    source_id           varchar(160) NOT NULL,
    topic_code          varchar(40) NOT NULL,
    sanitized_fact_snapshot varchar(280) NOT NULL,
    evidence_confidence real NOT NULL,
    consent_snapshot    jsonb NOT NULL,
    actually_used       boolean NOT NULL DEFAULT false,
    created_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (source_type IN ('GAMING_EVENT', 'MATCH_STAT', 'HIGHLIGHT', 'PARTY_LORE',
        'HARMLESS_QUOTE', 'SELF_DESCRIPTION')),
    CHECK (evidence_confidence BETWEEN 0 AND 1),
    UNIQUE (candidate_id, source_type, source_id)
);

CREATE TABLE safety_incidents (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id          uuid NOT NULL REFERENCES roast_sessions(id) ON DELETE CASCADE,
    round_id            uuid REFERENCES roast_rounds(id) ON DELETE SET NULL,
    reporter_player_id  bigint REFERENCES players(id) ON DELETE SET NULL,
    detected_by         varchar(16) NOT NULL,
    incident_type       varchar(32) NOT NULL,
    candidate_text_sha256 char(64),
    risk_flags          text[] NOT NULL DEFAULT '{}',
    action_taken        varchar(32) NOT NULL,
    detail_code         varchar(80),
    created_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (detected_by IN ('SYSTEM', 'MODEL_REVIEW', 'PLAYER')),
    CHECK (incident_type IN ('SENSITIVE_TOPIC', 'UNSUPPORTED_CLAIM', 'WRONG_PLAYER',
        'TOO_HARSH', 'REAL_CONFLICT', 'CONSENT_REVOKED', 'PROMPT_INJECTION', 'REPETITIVE')),
    CHECK (action_taken IN ('CANDIDATE_REJECTED', 'ROUND_SKIPPED', 'INTENSITY_REDUCED',
        'TARGET_BLOCKED', 'SESSION_PAUSED', 'SESSION_CANCELLED'))
);

CREATE TABLE roast_generation_jobs (
    id                  uuid PRIMARY KEY,
    session_id          uuid NOT NULL REFERENCES roast_sessions(id) ON DELETE CASCADE,
    round_id            uuid REFERENCES roast_rounds(id) ON DELETE CASCADE,
    job_type            varchar(20) NOT NULL,
    status              varchar(16) NOT NULL DEFAULT 'QUEUED',
    idempotency_key     varchar(200) NOT NULL UNIQUE,
    attempt_count       integer NOT NULL DEFAULT 0,
    max_attempts        integer NOT NULL DEFAULT 2,
    next_attempt_at     timestamptz NOT NULL DEFAULT now(),
    lease_owner         varchar(100),
    lease_expires_at    timestamptz,
    consent_snapshot_hash char(64) NOT NULL,
    error_code          varchar(64),
    created_at          timestamptz NOT NULL DEFAULT now(),
    completed_at        timestamptz,
    CHECK (job_type IN ('GENERATE', 'REGENERATE', 'JUDGE', 'RECAP')),
    CHECK (status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')),
    CHECK (attempt_count BETWEEN 0 AND 5),
    CHECK (max_attempts BETWEEN 1 AND 5)
);

CREATE INDEX ix_roast_generation_jobs_worker
    ON roast_generation_jobs (status, next_attempt_at, created_at)
    WHERE status IN ('QUEUED', 'RUNNING');

-- Service-level invariants:
-- 1. A session has exactly three distinct players from the same server; all must be READY at the
--    current consent_version before ACTIVE.
-- 2. The mandatory hard-block category set can be extended by a player but never reduced.
-- 3. Revocation pauses/cancels pending jobs, invalidates context snapshots and removes the player
--    from future targeting immediately.
-- 4. Rejected unsafe candidate text is never persisted; safety_incidents stores only its hash/flags.
-- 5. Every displayed candidate passed deterministic filters and the independent safety reviewer.
-- 6. At most one CONFIRMED, LOW, ROAST-allowed Party Lore item can be used per candidate.
