-- Highlight Generator reference schema for PostgreSQL 16.
-- Design artifact only. Production implementation uses SQLAlchemy + Alembic.

CREATE TABLE recording_sources (
    id                  uuid PRIMARY KEY,
    server_id           bigint NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    owner_player_id     bigint NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    source_type         varchar(32) NOT NULL,
    display_name        varchar(100) NOT NULL,
    consent_state       varchar(20) NOT NULL DEFAULT 'ENABLED',
    settings            jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_enabled          boolean NOT NULL DEFAULT true,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (source_type IN ('MANUAL_UPLOAD', 'OBS_REPLAY_BUFFER', 'DISCORD_SCREEN_RECORDING',
        'AUDIO_ONLY', 'FUTURE_CONNECTOR')),
    CHECK (consent_state IN ('ENABLED', 'CONFIRM_EACH_UPLOAD', 'DISABLED')),
    UNIQUE (server_id, owner_player_id, display_name)
);

CREATE TABLE recordings (
    id                  uuid PRIMARY KEY,
    server_id           bigint NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    session_id          uuid,
    source_id           uuid REFERENCES recording_sources(id) ON DELETE SET NULL,
    uploaded_by_player_id bigint NOT NULL REFERENCES players(id) ON DELETE RESTRICT,
    source_type         varchar(32) NOT NULL,
    original_filename  varchar(180) NOT NULL,
    declared_mime_type varchar(80) NOT NULL,
    detected_format     varchar(40),
    storage_key         varchar(300) UNIQUE,
    declared_byte_size bigint NOT NULL,
    byte_size           bigint,
    declared_sha256     char(64) NOT NULL,
    sha256              char(64),
    duration_ms         bigint,
    width               integer,
    height              integer,
    frame_rate          real,
    video_codec         varchar(40),
    audio_codec         varchar(40),
    audio_tracks        smallint,
    has_audio           boolean,
    capture_started_at  timestamptz,
    capture_ended_at    timestamptz,
    probe_payload       jsonb,
    status              varchar(24) NOT NULL DEFAULT 'AWAITING_UPLOAD',
    retention_until     timestamptz NOT NULL DEFAULT (now() + interval '14 days'),
    upload_expires_at   timestamptz NOT NULL DEFAULT (now() + interval '2 hours'),
    created_at          timestamptz NOT NULL DEFAULT now(),
    uploaded_at         timestamptz,
    probed_at           timestamptz,
    deleted_at          timestamptz,
    CHECK (source_type IN ('MANUAL_UPLOAD', 'OBS_REPLAY_BUFFER', 'DISCORD_SCREEN_RECORDING',
        'AUDIO_ONLY', 'FUTURE_CONNECTOR')),
    CHECK (declared_mime_type IN ('video/mp4', 'video/x-matroska', 'audio/wav', 'audio/mpeg')),
    CHECK (declared_byte_size BETWEEN 1 AND 1073741824),
    CHECK (byte_size IS NULL OR byte_size BETWEEN 1 AND 1073741824),
    CHECK (duration_ms IS NULL OR duration_ms BETWEEN 1 AND 900000),
    CHECK (width IS NULL OR width BETWEEN 1 AND 7680),
    CHECK (height IS NULL OR height BETWEEN 1 AND 4320),
    CHECK (frame_rate IS NULL OR frame_rate > 0 AND frame_rate <= 240),
    CHECK (audio_tracks IS NULL OR audio_tracks BETWEEN 0 AND 16),
    CHECK (status IN ('AWAITING_UPLOAD', 'UPLOADED', 'PROBING', 'READY', 'INVALID',
        'DELETION_QUEUED', 'DELETED')),
    CHECK (capture_ended_at IS NULL OR capture_started_at IS NULL OR capture_ended_at >= capture_started_at)
);

CREATE UNIQUE INDEX uq_recordings_server_hash
    ON recordings (server_id, sha256)
    WHERE sha256 IS NOT NULL AND status NOT IN ('DELETION_QUEUED', 'DELETED');
CREATE INDEX ix_recordings_session ON recordings (server_id, session_id, created_at DESC);
CREATE INDEX ix_recordings_retention ON recordings (retention_until)
    WHERE status NOT IN ('DELETION_QUEUED', 'DELETED');

CREATE TABLE event_markers (
    id                  uuid PRIMARY KEY,
    recording_id        uuid NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    created_by_player_id bigint REFERENCES players(id) ON DELETE SET NULL,
    external_marker_id  varchar(160) NOT NULL,
    source_type         varchar(24) NOT NULL,
    offset_ms           bigint,
    occurred_at         timestamptz,
    category_hint       varchar(24),
    participant_player_ids bigint[] NOT NULL DEFAULT '{}',
    summary             varchar(500),
    manual_priority     smallint NOT NULL DEFAULT 0,
    commentator_priority real,
    game_event_severity real,
    payload             jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (source_type IN ('MANUAL', 'COMMENTATOR', 'TRANSCRIPT', 'GAME_TELEMETRY', 'DISCORD_COMMAND')),
    CHECK (offset_ms IS NOT NULL OR occurred_at IS NOT NULL),
    CHECK (offset_ms IS NULL OR offset_ms >= 0),
    CHECK (category_hint IS NULL OR category_hint IN ('SKILL', 'COMEDY', 'FAILURE', 'CHAOS', 'LORE_WORTHY')),
    CHECK (manual_priority IN (0, 1)),
    CHECK (commentator_priority IS NULL OR commentator_priority BETWEEN 0 AND 1),
    CHECK (game_event_severity IS NULL OR game_event_severity BETWEEN 0 AND 1),
    UNIQUE (recording_id, external_marker_id)
);

CREATE INDEX ix_event_markers_timeline ON event_markers (recording_id, offset_ms);

CREATE TABLE transcripts (
    id                  uuid PRIMARY KEY,
    recording_id        uuid NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    language            varchar(12) NOT NULL DEFAULT 'tr',
    provider            varchar(64) NOT NULL,
    model               varchar(128) NOT NULL,
    prompt_version      varchar(40),
    status              varchar(20) NOT NULL DEFAULT 'QUEUED',
    full_text           text,
    input_audio_sha256  char(64),
    duration_ms         bigint,
    diarization_mode    varchar(24) NOT NULL DEFAULT 'NONE',
    error_code          varchar(64),
    created_at          timestamptz NOT NULL DEFAULT now(),
    started_at          timestamptz,
    completed_at        timestamptz,
    CHECK (status IN ('QUEUED', 'RUNNING', 'READY', 'FAILED', 'DELETED')),
    CHECK (diarization_mode IN ('NONE', 'SEPARATE_TRACKS', 'UNCONFIRMED_SPEAKERS', 'PLAYER_CONFIRMED')),
    CHECK (duration_ms IS NULL OR duration_ms > 0),
    UNIQUE (recording_id, provider, model, input_audio_sha256)
);

CREATE TABLE transcript_segments (
    id                  uuid PRIMARY KEY,
    transcript_id       uuid NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    sequence_number     integer NOT NULL,
    start_ms            bigint NOT NULL,
    end_ms              bigint NOT NULL,
    text                text NOT NULL,
    speaker_label       varchar(40) NOT NULL DEFAULT 'UNKNOWN',
    player_id           bigint REFERENCES players(id) ON DELETE SET NULL,
    speaker_mapping_confirmed boolean NOT NULL DEFAULT false,
    confidence          real NOT NULL,
    reaction_flags      text[] NOT NULL DEFAULT '{}',
    created_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (sequence_number >= 0),
    CHECK (start_ms >= 0 AND end_ms > start_ms),
    CHECK (confidence BETWEEN 0 AND 1),
    CHECK ((player_id IS NULL) OR speaker_mapping_confirmed),
    UNIQUE (transcript_id, sequence_number)
);

CREATE INDEX ix_transcript_segments_timeline
    ON transcript_segments (transcript_id, start_ms);

CREATE TABLE highlight_candidates (
    id                  uuid PRIMARY KEY,
    recording_id        uuid NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    primary_marker_id   uuid REFERENCES event_markers(id) ON DELETE SET NULL,
    start_ms            bigint NOT NULL,
    end_ms              bigint NOT NULL,
    anchor_ms           bigint NOT NULL,
    score               real NOT NULL,
    primary_category    varchar(24) NOT NULL,
    title               varchar(120),
    description         varchar(300),
    participant_player_ids bigint[] NOT NULL DEFAULT '{}',
    signal_scores       jsonb NOT NULL,
    lore_candidate      boolean NOT NULL DEFAULT false,
    meme_candidate      boolean NOT NULL DEFAULT false,
    suggested_pre_padding_ms integer NOT NULL DEFAULT 10000,
    suggested_post_padding_ms integer NOT NULL DEFAULT 6000,
    status              varchar(24) NOT NULL DEFAULT 'PROPOSED',
    analysis_version    varchar(40) NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (start_ms >= 0 AND end_ms > start_ms),
    CHECK (anchor_ms BETWEEN start_ms AND end_ms),
    CHECK (end_ms - start_ms <= 60000),
    CHECK (score BETWEEN 0 AND 1),
    CHECK (primary_category IN ('SKILL', 'COMEDY', 'FAILURE', 'CHAOS', 'LORE_WORTHY')),
    CHECK (suggested_pre_padding_ms BETWEEN 0 AND 30000),
    CHECK (suggested_post_padding_ms BETWEEN 0 AND 20000),
    CHECK (status IN ('PROPOSED', 'APPROVED', 'REJECTED', 'RENDERING', 'RENDERED', 'DELETED'))
);

CREATE INDEX ix_highlight_candidates_recording
    ON highlight_candidates (recording_id, score DESC);

CREATE TABLE rendered_highlights (
    id                  uuid PRIMARY KEY,
    candidate_id        uuid REFERENCES highlight_candidates(id) ON DELETE SET NULL,
    server_id           bigint NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    session_id          uuid,
    created_by_player_id bigint NOT NULL REFERENCES players(id) ON DELETE RESTRICT,
    variant             varchar(24) NOT NULL,
    title               varchar(120) NOT NULL,
    description         varchar(300) NOT NULL,
    storage_key         varchar(300) NOT NULL UNIQUE,
    thumbnail_storage_key varchar(300) NOT NULL UNIQUE,
    mime_type           varchar(40) NOT NULL DEFAULT 'video/mp4',
    byte_size           bigint NOT NULL,
    sha256              char(64) NOT NULL,
    duration_ms         bigint NOT NULL,
    width               integer NOT NULL,
    height              integer NOT NULL,
    video_codec         varchar(40) NOT NULL,
    audio_codec         varchar(40),
    render_parameters   jsonb NOT NULL,
    render_version      varchar(40) NOT NULL,
    status              varchar(24) NOT NULL DEFAULT 'READY',
    delivery_channel    varchar(20),
    delivery_external_id varchar(255),
    retention_until     timestamptz NOT NULL DEFAULT (now() + interval '90 days'),
    created_at          timestamptz NOT NULL DEFAULT now(),
    delivered_at        timestamptz,
    saved_at            timestamptz,
    deleted_at          timestamptz,
    CHECK (variant IN ('LANDSCAPE', 'VERTICAL', 'SUBTITLED', 'INTRO_TITLE', 'REACTION_TEXT', 'COMPILATION')),
    CHECK (mime_type = 'video/mp4'),
    CHECK (byte_size > 0),
    CHECK (duration_ms BETWEEN 1 AND 180000),
    CHECK (width BETWEEN 320 AND 3840),
    CHECK (height BETWEEN 320 AND 3840),
    CHECK (status IN ('READY', 'DELIVERED', 'SAVED', 'DELETION_QUEUED', 'DELETED')),
    CHECK (delivery_channel IS NULL OR delivery_channel IN ('WEB', 'MATRIX', 'DISCORD'))
);

CREATE INDEX ix_rendered_highlights_session
    ON rendered_highlights (server_id, session_id, created_at DESC)
    WHERE status <> 'DELETED';

CREATE TABLE highlight_feedback (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rendered_highlight_id uuid NOT NULL REFERENCES rendered_highlights(id) ON DELETE CASCADE,
    player_id           bigint NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    feedback_type       varchar(24) NOT NULL,
    details             varchar(500),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (feedback_type IN ('GOOD', 'WRONG_MOMENT', 'TRIM_EARLIER', 'TRIM_LATER', 'TOO_LONG', 'SAVE')),
    UNIQUE (rendered_highlight_id, player_id)
);

CREATE TABLE highlight_lore_links (
    rendered_highlight_id uuid NOT NULL REFERENCES rendered_highlights(id) ON DELETE CASCADE,
    lore_id             bigint NOT NULL REFERENCES lore_entries(id) ON DELETE RESTRICT,
    link_type           varchar(20) NOT NULL,
    relevance_score     real NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (rendered_highlight_id, lore_id, link_type),
    CHECK (link_type IN ('REFERENCED', 'SOURCE_EVIDENCE')),
    CHECK (relevance_score BETWEEN 0 AND 1)
);

CREATE INDEX ix_highlight_lore_reverse
    ON highlight_lore_links (lore_id, created_at DESC);

CREATE TABLE processing_jobs (
    id                  uuid PRIMARY KEY,
    recording_id        uuid REFERENCES recordings(id) ON DELETE CASCADE,
    candidate_id        uuid REFERENCES highlight_candidates(id) ON DELETE CASCADE,
    rendered_highlight_id uuid REFERENCES rendered_highlights(id) ON DELETE CASCADE,
    parent_job_id       uuid REFERENCES processing_jobs(id) ON DELETE SET NULL,
    stage               varchar(24) NOT NULL,
    status              varchar(20) NOT NULL DEFAULT 'QUEUED',
    progress            real NOT NULL DEFAULT 0,
    idempotency_key     varchar(200) NOT NULL,
    parameters_hash     char(64) NOT NULL,
    tool_version        varchar(120),
    input_snapshot      jsonb NOT NULL DEFAULT '{}'::jsonb,
    output_snapshot     jsonb,
    attempt_count       integer NOT NULL DEFAULT 0,
    max_attempts        integer NOT NULL DEFAULT 2,
    next_attempt_at     timestamptz NOT NULL DEFAULT now(),
    lease_owner         varchar(100),
    lease_expires_at    timestamptz,
    heartbeat_at        timestamptz,
    error_code          varchar(64),
    error_detail        varchar(1000),
    created_at          timestamptz NOT NULL DEFAULT now(),
    started_at          timestamptz,
    completed_at        timestamptz,
    CHECK (recording_id IS NOT NULL OR candidate_id IS NOT NULL OR rendered_highlight_id IS NOT NULL),
    CHECK (stage IN ('UPLOAD', 'PROBE', 'EXTRACT_AUDIO', 'TRANSCRIBE', 'ANALYZE', 'TRIM',
        'SUBTITLE', 'RENDER', 'THUMBNAIL', 'DELIVER', 'DELETE')),
    CHECK (status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')),
    CHECK (progress BETWEEN 0 AND 1),
    CHECK (attempt_count BETWEEN 0 AND 10),
    CHECK (max_attempts BETWEEN 1 AND 10),
    UNIQUE (idempotency_key)
);

CREATE INDEX ix_processing_jobs_worker
    ON processing_jobs (status, next_attempt_at, created_at)
    WHERE status IN ('QUEUED', 'RUNNING');

-- Service-level invariants:
-- 1. Every source, player, recording, marker, candidate and artifact belongs to the same server.
-- 2. Marker/candidate timestamps are validated against the probed recording duration.
-- 3. File paths and FFmpeg filter arguments are generated from UUID-backed trusted storage keys.
-- 4. A Party Lore candidate is never created without an explicit player confirmation/API action.
-- 5. Deletion makes API access unavailable immediately, cancels queued work, then removes original,
--    derivatives, thumbnails, transcript text and temporary files asynchronously.
