"""Add the shared experience, event, job and media foundation."""

from alembic import op
import sqlalchemy as sa


revision = "0009_platform_foundation"
down_revision = "0008_server_join_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experience_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("module_type", sa.String(length=32), nullable=False),
        sa.Column("server_id", sa.Integer(), sa.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="SET NULL"), nullable=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="lobby"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_players", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("settings_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "owner_id",
            "module_type",
            "idempotency_key",
            name="uq_experience_session_create_idempotency",
        ),
    )
    op.create_index(
        "ix_experience_sessions_server_module_status",
        "experience_sessions",
        ["server_id", "module_type", "status"],
    )
    op.create_index("ix_experience_sessions_updated_at", "experience_sessions", ["updated_at"])

    op.create_table(
        "experience_session_players",
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("experience_sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("seat", sa.Integer(), nullable=False),
        sa.Column("ready", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("session_id", "seat", name="uq_experience_session_seat"),
    )
    op.create_index(
        "ix_experience_session_players_user",
        "experience_session_players",
        ["user_id", "session_id"],
    )

    op.create_table(
        "experience_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("experience_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("audience", sa.String(length=64), nullable=False, server_default="PUBLIC"),
        sa.Column("public_payload", sa.JSON(), nullable=False),
        sa.Column("encrypted_payload", sa.LargeBinary(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "sequence", name="uq_experience_event_sequence"),
        sa.UniqueConstraint("session_id", "idempotency_key", name="uq_experience_event_idempotency"),
    )
    op.create_index("ix_experience_events_replay", "experience_events", ["session_id", "sequence"])

    op.create_table(
        "background_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("module", sa.String(length=32), nullable=False),
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("experience_sessions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("input_ref", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_by", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("module", "idempotency_key", name="uq_background_job_idempotency"),
    )
    op.create_index(
        "ix_background_jobs_claim",
        "background_jobs",
        ["status", "next_attempt_at", "priority"],
    )
    op.create_index("ix_background_jobs_session", "background_jobs", ["session_id", "created_at"])

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("topic", sa.String(length=100), nullable=False),
        sa.Column("aggregate_type", sa.String(length=50), nullable=False),
        sa.Column("aggregate_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_outbox_events_pending", "outbox_events", ["published_at", "id"])

    op.create_table(
        "experience_ws_tickets",
        sa.Column("token_hash", sa.String(length=64), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("experience_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_experience_ws_tickets_expiry", "experience_ws_tickets", ["expires_at"])
    op.create_index(
        "ix_experience_ws_tickets_session_user",
        "experience_ws_tickets",
        ["session_id", "user_id"],
    )

    op.create_table(
        "media_assets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("server_id", sa.Integer(), sa.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("experience_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False, unique=True),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_media_assets_server_created", "media_assets", ["server_id", "created_at"])
    op.create_index("ix_media_assets_retention", "media_assets", ["retention_until"])
    op.create_index("ix_media_assets_sha", "media_assets", ["server_id", "sha256"])

    op.create_table(
        "ai_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("job_id", sa.String(length=36), sa.ForeignKey("background_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("logical_profile", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_runs_profile_created", "ai_runs", ["logical_profile", "created_at"])
    op.create_index("ix_ai_runs_job", "ai_runs", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_runs_job", table_name="ai_runs")
    op.drop_index("ix_ai_runs_profile_created", table_name="ai_runs")
    op.drop_table("ai_runs")
    op.drop_index("ix_media_assets_sha", table_name="media_assets")
    op.drop_index("ix_media_assets_retention", table_name="media_assets")
    op.drop_index("ix_media_assets_server_created", table_name="media_assets")
    op.drop_table("media_assets")
    op.drop_index("ix_experience_ws_tickets_session_user", table_name="experience_ws_tickets")
    op.drop_index("ix_experience_ws_tickets_expiry", table_name="experience_ws_tickets")
    op.drop_table("experience_ws_tickets")
    op.drop_index("ix_outbox_events_pending", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.drop_index("ix_background_jobs_session", table_name="background_jobs")
    op.drop_index("ix_background_jobs_claim", table_name="background_jobs")
    op.drop_table("background_jobs")
    op.drop_index("ix_experience_events_replay", table_name="experience_events")
    op.drop_table("experience_events")
    op.drop_index("ix_experience_session_players_user", table_name="experience_session_players")
    op.drop_table("experience_session_players")
    op.drop_index("ix_experience_sessions_updated_at", table_name="experience_sessions")
    op.drop_index("ix_experience_sessions_server_module_status", table_name="experience_sessions")
    op.drop_table("experience_sessions")
