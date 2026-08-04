-- Meme Generator reference schema for PostgreSQL 16.
-- Design artifact only. Production implementation uses SQLAlchemy + Alembic.

CREATE TABLE media_assets (
    id                  uuid PRIMARY KEY,
    server_id           bigint REFERENCES servers(id) ON DELETE CASCADE,
    created_by_player_id bigint REFERENCES players(id) ON DELETE SET NULL,
    asset_kind          varchar(24) NOT NULL,
    storage_key         varchar(300) NOT NULL UNIQUE,
    original_filename  varchar(180),
    mime_type           varchar(80) NOT NULL,
    byte_size           bigint NOT NULL,
    width               integer,
    height              integer,
    sha256              char(64) NOT NULL,
    status              varchar(16) NOT NULL DEFAULT 'ACTIVE',
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    deleted_at          timestamptz,
    CHECK (asset_kind IN ('TEMPLATE_SOURCE', 'SCREENSHOT', 'RENDERED_MEME', 'PREVIEW')),
    CHECK (mime_type IN ('image/png', 'image/jpeg', 'image/webp')),
    CHECK (byte_size > 0 AND byte_size <= 26214400),
    CHECK (width IS NULL OR width BETWEEN 1 AND 10000),
    CHECK (height IS NULL OR height BETWEEN 1 AND 10000),
    CHECK (status IN ('ACTIVE', 'QUARANTINED', 'DELETED')),
    UNIQUE NULLS NOT DISTINCT (server_id, sha256, asset_kind)
);

CREATE INDEX ix_media_assets_server_created
    ON media_assets (server_id, created_at DESC)
    WHERE status = 'ACTIVE';

CREATE TABLE meme_templates (
    id                  uuid PRIMARY KEY,
    server_id           bigint REFERENCES servers(id) ON DELETE CASCADE,
    template_key        varchar(80) NOT NULL,
    version             integer NOT NULL DEFAULT 1,
    name                varchar(120) NOT NULL,
    categories          text[] NOT NULL,
    image_asset_id      uuid NOT NULL REFERENCES media_assets(id) ON DELETE RESTRICT,
    caption_zones       jsonb NOT NULL,
    safe_text_limits    jsonb NOT NULL,
    canvas_width        integer NOT NULL,
    canvas_height       integer NOT NULL,
    tags                text[] NOT NULL DEFAULT '{}',
    required_context    text[] NOT NULL DEFAULT '{}',
    recent_use_cooldown_hours integer NOT NULL DEFAULT 168,
    suitability_rules   jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_builtin          boolean NOT NULL DEFAULT false,
    is_enabled          boolean NOT NULL DEFAULT true,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (version >= 1),
    CHECK (canvas_width BETWEEN 320 AND 4096),
    CHECK (canvas_height BETWEEN 320 AND 4096),
    CHECK (recent_use_cooldown_hours BETWEEN 0 AND 8760),
    UNIQUE NULLS NOT DISTINCT (server_id, template_key, version)
);

CREATE INDEX ix_meme_templates_categories ON meme_templates USING gin (categories);
CREATE INDEX ix_meme_templates_tags ON meme_templates USING gin (tags);

CREATE TABLE meme_generation_jobs (
    id                  uuid PRIMARY KEY,
    server_id           bigint NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    session_id          uuid,
    submitted_by_player_id bigint NOT NULL REFERENCES players(id) ON DELETE RESTRICT,
    external_event_id   varchar(160) NOT NULL,
    source_type         varchar(24) NOT NULL,
    input_event         jsonb NOT NULL,
    screenshot_asset_id uuid REFERENCES media_assets(id) ON DELETE SET NULL,
    job_type            varchar(20) NOT NULL DEFAULT 'SINGLE_MEME',
    status              varchar(24) NOT NULL DEFAULT 'QUEUED',
    meme_worthy         boolean,
    meme_worthiness_score real,
    reasoning_code      varchar(64),
    selected_category   varchar(40),
    selected_template_id uuid REFERENCES meme_templates(id) ON DELETE SET NULL,
    requested_harshness smallint NOT NULL DEFAULT 1,
    effective_harshness smallint,
    model_profile       varchar(80),
    provider_model      varchar(160),
    prompt_version      varchar(40),
    input_tokens        integer,
    output_tokens       integer,
    latency_ms          integer,
    idempotency_key     varchar(200) NOT NULL,
    lease_owner         varchar(100),
    lease_expires_at    timestamptz,
    attempt_count       integer NOT NULL DEFAULT 0,
    error_code          varchar(64),
    error_detail        varchar(500),
    created_at          timestamptz NOT NULL DEFAULT now(),
    started_at          timestamptz,
    completed_at        timestamptz,
    CHECK (source_type IN ('MANUAL', 'COMMENTARY_EVENT', 'HIGHLIGHT', 'GAME_CONNECTOR', 'TRANSCRIPT')),
    CHECK (job_type IN ('SINGLE_MEME', 'SESSION_PACK')),
    CHECK (status IN ('QUEUED', 'RUNNING', 'CANDIDATES_READY', 'RENDERING', 'COMPLETED',
        'NOT_WORTHY', 'FAILED', 'CANCELLED', 'DELETED')),
    CHECK (meme_worthiness_score IS NULL OR meme_worthiness_score BETWEEN 0 AND 1),
    CHECK (requested_harshness BETWEEN 0 AND 3),
    CHECK (effective_harshness IS NULL OR effective_harshness BETWEEN 0 AND 3),
    CHECK (attempt_count BETWEEN 0 AND 5),
    CHECK (input_tokens IS NULL OR input_tokens >= 0),
    CHECK (output_tokens IS NULL OR output_tokens >= 0),
    CHECK (latency_ms IS NULL OR latency_ms >= 0),
    UNIQUE (server_id, idempotency_key),
    UNIQUE (server_id, external_event_id, job_type)
);

CREATE INDEX ix_meme_jobs_worker
    ON meme_generation_jobs (status, created_at)
    WHERE status IN ('QUEUED', 'RUNNING', 'RENDERING');
CREATE INDEX ix_meme_jobs_session
    ON meme_generation_jobs (server_id, session_id, created_at DESC);

CREATE TABLE meme_caption_candidates (
    id                  uuid PRIMARY KEY,
    job_id              uuid NOT NULL REFERENCES meme_generation_jobs(id) ON DELETE CASCADE,
    template_id         uuid NOT NULL REFERENCES meme_templates(id) ON DELETE RESTRICT,
    category            varchar(40) NOT NULL,
    rank                smallint NOT NULL,
    captions            jsonb NOT NULL,
    target_player_id    bigint REFERENCES players(id) ON DELETE SET NULL,
    harshness           smallint NOT NULL,
    lore_reference_ids  bigint[] NOT NULL DEFAULT '{}',
    quality_score       real NOT NULL,
    safety_state        varchar(20) NOT NULL DEFAULT 'PENDING',
    phrase_hash         char(64) NOT NULL,
    reasoning_code      varchar(64) NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (rank BETWEEN 1 AND 10),
    CHECK (harshness BETWEEN 0 AND 3),
    CHECK (quality_score BETWEEN 0 AND 1),
    CHECK (safety_state IN ('PENDING', 'APPROVED', 'REJECTED', 'REPETITIVE')),
    UNIQUE (job_id, rank),
    UNIQUE (job_id, phrase_hash)
);

CREATE INDEX ix_meme_caption_phrase
    ON meme_caption_candidates (phrase_hash, created_at DESC);

CREATE TABLE generated_memes (
    id                  uuid PRIMARY KEY,
    job_id              uuid NOT NULL REFERENCES meme_generation_jobs(id) ON DELETE RESTRICT,
    candidate_id        uuid NOT NULL REFERENCES meme_caption_candidates(id) ON DELETE RESTRICT,
    template_id         uuid NOT NULL REFERENCES meme_templates(id) ON DELETE RESTRICT,
    output_asset_id     uuid NOT NULL REFERENCES media_assets(id) ON DELETE RESTRICT,
    session_id          uuid,
    category            varchar(40) NOT NULL,
    target_player_id    bigint REFERENCES players(id) ON DELETE SET NULL,
    captions_snapshot   jsonb NOT NULL,
    template_version    integer NOT NULL,
    render_version      varchar(40) NOT NULL,
    status              varchar(20) NOT NULL DEFAULT 'READY',
    delivery_channel    varchar(20),
    delivery_external_id varchar(255),
    delivered_at        timestamptz,
    saved_at            timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    deleted_at          timestamptz,
    CHECK (template_version >= 1),
    CHECK (status IN ('READY', 'DELIVERED', 'SAVED', 'DELETION_QUEUED', 'DELETED')),
    CHECK (delivery_channel IS NULL OR delivery_channel IN ('WEB', 'MATRIX', 'DISCORD'))
);

CREATE INDEX ix_generated_memes_session
    ON generated_memes (session_id, created_at DESC)
    WHERE status <> 'DELETED';
CREATE INDEX ix_generated_memes_target
    ON generated_memes (target_player_id, created_at DESC)
    WHERE status <> 'DELETED';

CREATE TABLE meme_feedback (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    meme_id             uuid NOT NULL REFERENCES generated_memes(id) ON DELETE CASCADE,
    player_id           bigint NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    feedback_type       varchar(24) NOT NULL,
    details             varchar(500),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (feedback_type IN ('FUNNY', 'FORCED', 'TOO_HARSH', 'REPETITIVE', 'WRONG_CONTEXT', 'SAVE')),
    UNIQUE (meme_id, player_id)
);

CREATE TABLE meme_lore_links (
    meme_id             uuid NOT NULL REFERENCES generated_memes(id) ON DELETE CASCADE,
    lore_id             bigint NOT NULL REFERENCES lore_entries(id) ON DELETE RESTRICT,
    retrieval_score     real NOT NULL,
    actually_used       boolean NOT NULL DEFAULT false,
    created_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (meme_id, lore_id),
    CHECK (retrieval_score BETWEEN 0 AND 1)
);

CREATE INDEX ix_meme_lore_reverse ON meme_lore_links (lore_id, created_at DESC);

CREATE TABLE meme_template_usage (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    template_id         uuid NOT NULL REFERENCES meme_templates(id) ON DELETE RESTRICT,
    meme_id             uuid NOT NULL REFERENCES generated_memes(id) ON DELETE CASCADE,
    server_id           bigint NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    session_id          uuid,
    category            varchar(40) NOT NULL,
    target_player_id    bigint REFERENCES players(id) ON DELETE SET NULL,
    used_at             timestamptz NOT NULL DEFAULT now(),
    UNIQUE (meme_id)
);

CREATE INDEX ix_meme_template_usage_recent
    ON meme_template_usage (server_id, template_id, used_at DESC);
CREATE INDEX ix_meme_format_target_recent
    ON meme_template_usage (server_id, target_player_id, used_at DESC);

-- Service-level invariants:
-- 1. Every player, session, screenshot and template must belong to the request's server.
-- 2. Built-in templates have server_id NULL and code-owned JSON; public APIs cannot edit them.
-- 3. media_assets.storage_key is generated by the service and never accepted from clients.
-- 4. Caption/lore/target policies are rechecked immediately before render and delivery.
-- 5. Deletion marks generated_memes and media_assets unavailable immediately, then removes bytes
--    asynchronously; feedback may remain only as an anonymized aggregate.
