-- Party Lore reference schema for PostgreSQL 16.
-- This is a design artifact, not an Alembic migration. Production migrations
-- should reproduce these constraints with the repository's SQLAlchemy models.

CREATE TABLE players (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    server_id           bigint NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    user_id             bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    display_name        varchar(64) NOT NULL,
    is_active           boolean NOT NULL DEFAULT true,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (server_id, user_id),
    UNIQUE (server_id, id)
);

CREATE TABLE raw_events (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    server_id           bigint NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    submitted_by_id     bigint REFERENCES players(id) ON DELETE SET NULL,
    source_type         varchar(32) NOT NULL,
    source_external_id  varchar(255),
    content             text NOT NULL,
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
    intentionally_submitted boolean NOT NULL DEFAULT false,
    occurred_at         timestamptz,
    expires_at          timestamptz NOT NULL DEFAULT (now() + interval '30 days'),
    processing_state    varchar(24) NOT NULL DEFAULT 'PENDING',
    content_sha256      char(64) NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    processed_at        timestamptz,
    CHECK (source_type IN ('MANUAL_NOTE', 'COMMENTATOR_EVENT', 'MATCH_SUMMARY',
        'HIGHLIGHT_TRANSCRIPT', 'SUBMITTED_MESSAGE', 'MEME_METADATA', 'SYSTEM_EVENT')),
    CHECK (processing_state IN ('PENDING', 'PROCESSED', 'REJECTED', 'PURGED')),
    UNIQUE NULLS NOT DISTINCT (server_id, source_type, source_external_id)
);

CREATE INDEX ix_raw_events_expiry ON raw_events (expires_at)
    WHERE processing_state <> 'PURGED';
CREATE INDEX ix_raw_events_server_created ON raw_events (server_id, created_at DESC);

CREATE TABLE lore_candidates (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    server_id           bigint NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    raw_event_id        bigint NOT NULL REFERENCES raw_events(id) ON DELETE CASCADE,
    title               varchar(120) NOT NULL,
    summary             text NOT NULL,
    category            varchar(40) NOT NULL,
    importance          real NOT NULL,
    humor_score         real NOT NULL,
    sensitivity         varchar(16) NOT NULL,
    confidence          real NOT NULL,
    tags                text[] NOT NULL DEFAULT '{}',
    participant_ids     bigint[] NOT NULL DEFAULT '{}',
    candidate_payload   jsonb NOT NULL,
    reason_code         varchar(64) NOT NULL,
    requires_confirmation boolean NOT NULL DEFAULT true,
    duplicate_of_lore_id bigint,
    state               varchar(24) NOT NULL DEFAULT 'PENDING',
    reviewed_by_id      bigint REFERENCES players(id) ON DELETE SET NULL,
    review_note         text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    reviewed_at         timestamptz,
    CHECK (importance BETWEEN 0 AND 1),
    CHECK (humor_score BETWEEN 0 AND 1),
    CHECK (confidence BETWEEN 0 AND 1),
    CHECK (sensitivity IN ('LOW', 'MEDIUM', 'HIGH', 'PROHIBITED')),
    CHECK (state IN ('PENDING', 'AUTO_ACCEPTED', 'CONFIRMED', 'REJECTED', 'EXPIRED')),
    UNIQUE (raw_event_id)
);

CREATE INDEX ix_lore_candidates_review_queue
    ON lore_candidates (server_id, created_at)
    WHERE state = 'PENDING';

CREATE TABLE lore_entries (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    server_id           bigint NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    title               varchar(120) NOT NULL,
    summary             text NOT NULL,
    category            varchar(40) NOT NULL,
    canonical_event_date timestamptz,
    confidence          real NOT NULL,
    importance          real NOT NULL,
    humor_score         real NOT NULL,
    sensitivity         varchar(16) NOT NULL,
    consent_state       varchar(24) NOT NULL,
    source_type         varchar(32) NOT NULL,
    status              varchar(24) NOT NULL DEFAULT 'ACTIVE',
    allowed_usage_types text[] NOT NULL DEFAULT ARRAY['PRIVATE_RECAP']::text[],
    tags                text[] NOT NULL DEFAULT '{}',
    search_document     tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(summary, '')), 'B') ||
        setweight(to_tsvector('simple', array_to_string(tags, ' ')), 'C')
    ) STORED,
    usage_count         integer NOT NULL DEFAULT 0,
    positive_feedback_count integer NOT NULL DEFAULT 0,
    negative_feedback_count integer NOT NULL DEFAULT 0,
    reference_strength  real NOT NULL DEFAULT 0.5,
    last_used_at        timestamptz,
    cooldown_until      timestamptz,
    pinned_at           timestamptz,
    archived_at         timestamptz,
    created_by_candidate_id bigint REFERENCES lore_candidates(id) ON DELETE SET NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    deleted_at          timestamptz,
    CHECK (category IN ('LEGENDARY_EVENT', 'REPEATED_FAILURE', 'RECURRING_BEHAVIOR',
        'NICKNAME_ORIGIN', 'QUOTE', 'RIVALRY', 'ACHIEVEMENT', 'BETRAYAL', 'RUNNING_JOKE',
        'GROUP_TRADITION', 'FAILED_STRATEGY', 'UNEXPECTED_SUCCESS', 'PLAYER_PREFERENCE',
        'HUMOR_BOUNDARY', 'SESSION_REFERENCE')),
    CHECK (confidence BETWEEN 0 AND 1),
    CHECK (importance BETWEEN 0 AND 1),
    CHECK (humor_score BETWEEN 0 AND 1),
    CHECK (reference_strength BETWEEN 0 AND 1),
    CHECK (sensitivity IN ('LOW', 'MEDIUM', 'HIGH', 'PROHIBITED')),
    CHECK (consent_state IN ('AUTO_ALLOWED', 'CONFIRM_REQUIRED', 'CONFIRMED',
        'RESTRICTED', 'NEVER_REFERENCE', 'DELETED')),
    CHECK (status IN ('ACTIVE', 'DISPUTED', 'ARCHIVED', 'MERGED', 'DELETED')),
    CHECK (usage_count >= 0)
);

ALTER TABLE lore_candidates
    ADD CONSTRAINT fk_candidate_duplicate
    FOREIGN KEY (duplicate_of_lore_id) REFERENCES lore_entries(id) ON DELETE SET NULL;

CREATE INDEX ix_lore_entries_active ON lore_entries (server_id, category, importance DESC)
    WHERE status = 'ACTIVE';
CREATE INDEX ix_lore_entries_search ON lore_entries USING gin (search_document);
CREATE INDEX ix_lore_entries_tags ON lore_entries USING gin (tags);
CREATE INDEX ix_lore_entries_allowed_usage ON lore_entries USING gin (allowed_usage_types);
CREATE INDEX ix_lore_entries_cooldown ON lore_entries (server_id, cooldown_until);

CREATE TABLE lore_participants (
    lore_id             bigint NOT NULL REFERENCES lore_entries(id) ON DELETE CASCADE,
    player_id           bigint NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    role                varchar(24) NOT NULL DEFAULT 'INVOLVED',
    mention_name        varchar(64),
    player_consent_state varchar(24) NOT NULL DEFAULT 'AUTO_ALLOWED',
    created_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (lore_id, player_id),
    CHECK (role IN ('SUBJECT', 'WITNESS', 'AUTHOR', 'TARGET', 'INVOLVED')),
    CHECK (player_consent_state IN ('AUTO_ALLOWED', 'CONFIRM_REQUIRED', 'CONFIRMED',
        'RESTRICTED', 'NEVER_REFERENCE', 'DELETED'))
);

CREATE INDEX ix_lore_participants_player ON lore_participants (player_id, lore_id);

CREATE TABLE lore_evidence (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lore_id             bigint NOT NULL REFERENCES lore_entries(id) ON DELETE CASCADE,
    raw_event_id        bigint REFERENCES raw_events(id) ON DELETE SET NULL,
    source_type         varchar(32) NOT NULL,
    source_external_id  varchar(255),
    excerpt             text,
    evidence_hash       char(64) NOT NULL,
    reliability         real NOT NULL DEFAULT 0.5,
    observed_at         timestamptz,
    submitted_by_id     bigint REFERENCES players(id) ON DELETE SET NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (reliability BETWEEN 0 AND 1),
    CHECK (char_length(coalesce(excerpt, '')) <= 1000)
);

CREATE INDEX ix_lore_evidence_lore ON lore_evidence (lore_id);

CREATE TABLE lore_aliases (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lore_id             bigint NOT NULL REFERENCES lore_entries(id) ON DELETE CASCADE,
    alias               varchar(120) NOT NULL,
    normalized_alias    varchar(120) NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (lore_id, normalized_alias)
);

CREATE INDEX ix_lore_aliases_lookup ON lore_aliases (normalized_alias);

CREATE TABLE lore_relationships (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    from_lore_id        bigint NOT NULL REFERENCES lore_entries(id) ON DELETE CASCADE,
    to_lore_id          bigint NOT NULL REFERENCES lore_entries(id) ON DELETE CASCADE,
    relationship_type   varchar(32) NOT NULL,
    confidence          real NOT NULL DEFAULT 1.0,
    created_by          varchar(16) NOT NULL DEFAULT 'SYSTEM',
    created_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (from_lore_id <> to_lore_id),
    CHECK (relationship_type IN ('SEQUEL_TO', 'SIMILAR_TO', 'CAUSED_BY', 'REPEATED_BY',
        'CONTRADICTS', 'NICKNAME_ORIGIN', 'PART_OF_RUNNING_JOKE')),
    CHECK (confidence BETWEEN 0 AND 1),
    CHECK (created_by IN ('SYSTEM', 'PLAYER', 'LLM')),
    UNIQUE (from_lore_id, to_lore_id, relationship_type)
);

CREATE INDEX ix_lore_relationships_reverse
    ON lore_relationships (to_lore_id, relationship_type);

CREATE TABLE lore_feedback (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lore_id             bigint NOT NULL REFERENCES lore_entries(id) ON DELETE CASCADE,
    player_id           bigint NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    feedback_type       varchar(32) NOT NULL,
    details             text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    resolved_at         timestamptz,
    CHECK (feedback_type IN ('ACCURATE', 'INACCURATE', 'FUNNY', 'NOT_FUNNY', 'OVERUSED',
        'WRONG_PLAYER', 'UNCOMFORTABLE', 'REQUEST_DELETE'))
);

CREATE INDEX ix_lore_feedback_unresolved ON lore_feedback (lore_id, created_at)
    WHERE resolved_at IS NULL;

CREATE TABLE lore_usage_history (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lore_id             bigint REFERENCES lore_entries(id) ON DELETE SET NULL,
    lore_title_snapshot varchar(120) NOT NULL,
    module              varchar(32) NOT NULL,
    request_id          varchar(128) NOT NULL,
    artifact_id         varchar(255),
    rendered_phrase_hash char(64),
    used_for_player_id  bigint REFERENCES players(id) ON DELETE SET NULL,
    outcome             varchar(24) NOT NULL DEFAULT 'USED',
    used_at             timestamptz NOT NULL DEFAULT now(),
    CHECK (module IN ('COMMENTARY', 'MEME', 'HIGHLIGHT', 'ROAST', 'BOARD_GAME',
        'HIDDEN_ROLE', 'SHARED_STORY', 'ESCAPE_ROOM', 'PRIVATE_RECAP')),
    CHECK (outcome IN ('USED', 'SKIPPED', 'REJECTED', 'REDACTED')),
    UNIQUE (request_id, lore_id)
);

CREATE INDEX ix_lore_usage_recent ON lore_usage_history (lore_id, used_at DESC);
CREATE INDEX ix_lore_usage_phrase_recent ON lore_usage_history (rendered_phrase_hash, used_at DESC);

CREATE TABLE player_humor_preferences (
    player_id           bigint PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
    allow_commentary    boolean NOT NULL DEFAULT true,
    allow_memes         boolean NOT NULL DEFAULT true,
    allow_roast_battle  boolean NOT NULL DEFAULT false,
    allow_private_recap boolean NOT NULL DEFAULT true,
    never_use_against_player boolean NOT NULL DEFAULT false,
    maximum_sensitivity varchar(16) NOT NULL DEFAULT 'LOW',
    blocked_categories  text[] NOT NULL DEFAULT '{}',
    blocked_tags        text[] NOT NULL DEFAULT '{}',
    updated_by_player_id bigint REFERENCES players(id) ON DELETE SET NULL,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (maximum_sensitivity IN ('LOW', 'MEDIUM', 'HIGH'))
);

CREATE TABLE lore_embeddings (
    lore_id             bigint NOT NULL REFERENCES lore_entries(id) ON DELETE CASCADE,
    provider            varchar(64) NOT NULL,
    model               varchar(128) NOT NULL,
    dimensions          integer NOT NULL,
    embedding           real[] NOT NULL,
    content_hash        char(64) NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (lore_id, provider, model),
    CHECK (dimensions > 0 AND dimensions <= 4096),
    CHECK (cardinality(embedding) = dimensions)
);

CREATE TABLE lore_merge_history (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_lore_id      bigint NOT NULL REFERENCES lore_entries(id) ON DELETE RESTRICT,
    target_lore_id      bigint NOT NULL REFERENCES lore_entries(id) ON DELETE RESTRICT,
    merged_by_player_id bigint REFERENCES players(id) ON DELETE SET NULL,
    reason              text NOT NULL,
    source_snapshot     jsonb NOT NULL,
    target_before_snapshot jsonb NOT NULL,
    target_after_snapshot jsonb NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (source_lore_id <> target_lore_id)
);

CREATE INDEX ix_lore_merge_history_target ON lore_merge_history (target_lore_id, created_at DESC);

-- Cross-server integrity (participant/lore pairs belonging to the same server) is easiest
-- to enforce in the service transaction in the MVP. If this grows into a multi-tenant product,
-- promote server_id into the join-table keys and enforce it with composite foreign keys.
