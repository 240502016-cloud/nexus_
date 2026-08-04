"""Add AI Commentator module state."""

from alembic import op
import sqlalchemy as sa


revision = "0011_ai_commentator"
down_revision = "0010_party_lore"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commentator_player_preferences",
        sa.Column(
            "server_id",
            sa.Integer(),
            sa.ForeignKey("servers.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("commentary_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_targeted_jokes", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_lore_references", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("maximum_harshness", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("preferred_humor_styles", sa.JSON(), nullable=False),
        sa.Column("blocked_topics", sa.JSON(), nullable=False),
        sa.Column("tts_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "maximum_harshness >= 0 AND maximum_harshness <= 3",
            name="ck_commentator_preference_harshness",
        ),
    )

    op.create_table(
        "commentator_session_players",
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("experience_sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("preference_snapshot", sa.JSON(), nullable=False),
        sa.Column("targeted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_present", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "targeted_count >= 0", name="ck_commentator_session_targeted_count"
        ),
    )
    op.create_index(
        "ix_commentator_session_players_user",
        "commentator_session_players",
        ["user_id", "session_id"],
    )

    op.create_table(
        "commentator_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("experience_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_event_id", sa.String(length=160), nullable=False),
        sa.Column("schema_version", sa.String(length=8), nullable=False, server_default="1.0"),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_player_ids", sa.JSON(), nullable=False),
        sa.Column("target_player_ids", sa.JSON(), nullable=False),
        sa.Column("normalized_summary", sa.String(length=240), nullable=False),
        sa.Column("game_context", sa.JSON(), nullable=False),
        sa.Column("normalized_attributes", sa.JSON(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("source_confidence", sa.Float(), nullable=False),
        sa.Column("novelty_score", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("trigger_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("trigger_decision", sa.String(length=24), nullable=False),
        sa.Column("deduplication_key", sa.String(length=64), nullable=False),
        sa.Column("processing_state", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "importance >= 0 AND importance <= 1", name="ck_commentator_event_importance"
        ),
        sa.CheckConstraint(
            "source_confidence >= 0 AND source_confidence <= 1",
            name="ck_commentator_event_confidence",
        ),
        sa.CheckConstraint(
            "novelty_score >= 0 AND novelty_score <= 1", name="ck_commentator_event_novelty"
        ),
        sa.CheckConstraint(
            "trigger_score >= 0 AND trigger_score <= 1", name="ck_commentator_event_trigger"
        ),
        sa.UniqueConstraint("session_id", "external_event_id", name="uq_commentator_event_external"),
    )
    op.create_index(
        "ix_commentator_events_recent", "commentator_events", ["session_id", "occurred_at"]
    )
    op.create_index(
        "ix_commentator_events_dedup",
        "commentator_events",
        ["session_id", "deduplication_key", "occurred_at"],
    )
    op.create_index(
        "ix_commentator_events_state", "commentator_events", ["processing_state", "created_at"]
    )

    op.create_table(
        "generated_commentary",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("experience_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "primary_event_id",
            sa.String(length=36),
            sa.ForeignKey("commentator_events.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "job_id",
            sa.String(length=36),
            sa.ForeignKey("background_jobs.id", ondelete="SET NULL"),
            nullable=True,
            unique=True,
        ),
        sa.Column("source_event_ids", sa.JSON(), nullable=False),
        sa.Column("profile_key", sa.String(length=64), nullable=False),
        sa.Column("should_comment", sa.Boolean(), nullable=False),
        sa.Column("commentary_text", sa.String(length=240), nullable=True),
        sa.Column(
            "target_player_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tone", sa.String(length=16), nullable=True),
        sa.Column("lore_references", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reason_code", sa.String(length=32), nullable=False),
        sa.Column("model_profile", sa.String(length=80), nullable=False, server_default="commentary-live"),
        sa.Column("provider_model", sa.String(length=160), nullable=True),
        sa.Column("prompt_version", sa.String(length=40), nullable=False, server_default="commentator-live-v1"),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("phrase_hash", sa.String(length=64), nullable=True),
        sa.Column("dispatch_state", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("dispatch_error_code", sa.String(length=64), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_generated_commentary_confidence"
        ),
        sa.CheckConstraint(
            "(should_comment AND commentary_text IS NOT NULL) OR "
            "(NOT should_comment AND commentary_text IS NULL)",
            name="ck_generated_commentary_shape",
        ),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0", name="ck_generated_commentary_latency"
        ),
    )
    op.create_index(
        "ix_generated_commentary_history",
        "generated_commentary",
        ["session_id", "created_at"],
    )
    op.create_index(
        "ix_generated_commentary_target",
        "generated_commentary",
        ["session_id", "target_player_id", "created_at"],
    )
    op.create_index(
        "ix_generated_commentary_phrase",
        "generated_commentary",
        ["session_id", "phrase_hash", "created_at"],
    )

    op.create_table(
        "commentary_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "commentary_id",
            sa.String(length=36),
            sa.ForeignKey("generated_commentary.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("feedback_type", sa.String(length=24), nullable=False),
        sa.Column("details", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("commentary_id", "user_id", name="uq_commentary_feedback_user"),
    )

    op.create_table(
        "commentary_cooldowns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("experience_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("scope_key", sa.String(length=160), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.CheckConstraint("usage_count >= 1", name="ck_commentary_cooldown_usage"),
        sa.UniqueConstraint("session_id", "scope_type", "scope_key", name="uq_commentary_cooldown"),
    )
    op.create_index(
        "ix_commentary_cooldowns_active",
        "commentary_cooldowns",
        ["session_id", "cooldown_until"],
    )


def downgrade() -> None:
    op.drop_index("ix_commentary_cooldowns_active", table_name="commentary_cooldowns")
    op.drop_table("commentary_cooldowns")
    op.drop_table("commentary_feedback")
    op.drop_index("ix_generated_commentary_phrase", table_name="generated_commentary")
    op.drop_index("ix_generated_commentary_target", table_name="generated_commentary")
    op.drop_index("ix_generated_commentary_history", table_name="generated_commentary")
    op.drop_table("generated_commentary")
    op.drop_index("ix_commentator_events_state", table_name="commentator_events")
    op.drop_index("ix_commentator_events_dedup", table_name="commentator_events")
    op.drop_index("ix_commentator_events_recent", table_name="commentator_events")
    op.drop_table("commentator_events")
    op.drop_index(
        "ix_commentator_session_players_user", table_name="commentator_session_players"
    )
    op.drop_table("commentator_session_players")
    op.drop_table("commentator_player_preferences")
