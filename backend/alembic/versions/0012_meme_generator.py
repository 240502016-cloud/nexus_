"""Add Meme Generator module state."""

from alembic import op
import sqlalchemy as sa


revision = "0012_meme_generator"
down_revision = "0011_ai_commentator"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meme_player_preferences",
        sa.Column("server_id", sa.Integer(), sa.ForeignKey("servers.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("memes_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_as_target", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_lore_references", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("maximum_harshness", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("blocked_topics", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "maximum_harshness >= 0 AND maximum_harshness <= 2",
            name="ck_meme_preference_harshness",
        ),
    )

    op.create_table(
        "meme_generations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("server_id", sa.Integer(), sa.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("experience_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("requested_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("background_job_id", sa.String(length=36), sa.ForeignKey("background_jobs.id", ondelete="SET NULL"), nullable=True, unique=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("external_event_id", sa.String(length=160), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("event_snapshot", sa.JSON(), nullable=False),
        sa.Column("preferred_formats", sa.JSON(), nullable=False),
        sa.Column("desired_harshness", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("meme_worthiness_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reasoning_code", sa.String(length=40), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=True),
        sa.Column("eligible_template_keys", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("meme_worthiness_score >= 0 AND meme_worthiness_score <= 1", name="ck_meme_generation_score"),
        sa.CheckConstraint("desired_harshness >= 0 AND desired_harshness <= 2", name="ck_meme_generation_harshness"),
        sa.UniqueConstraint("server_id", "external_event_id", name="uq_meme_generation_event"),
        sa.UniqueConstraint("server_id", "requested_by_id", "idempotency_key", name="uq_meme_generation_request"),
    )
    op.create_index("ix_meme_generations_server_created", "meme_generations", ["server_id", "created_at"])
    op.create_index("ix_meme_generations_status", "meme_generations", ["status", "created_at"])

    op.create_table(
        "meme_caption_candidates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("generation_id", sa.String(length=36), sa.ForeignKey("meme_generations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("template_key", sa.String(length=64), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("captions", sa.JSON(), nullable=False),
        sa.Column("target_player_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lore_references", sa.JSON(), nullable=False),
        sa.Column("harshness", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("phrase_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rank >= 1 AND rank <= 3", name="ck_meme_candidate_rank"),
        sa.CheckConstraint("harshness >= 0 AND harshness <= 2", name="ck_meme_candidate_harshness"),
        sa.CheckConstraint("quality_score >= 0 AND quality_score <= 1", name="ck_meme_candidate_quality"),
        sa.UniqueConstraint("generation_id", "rank", name="uq_meme_candidate_rank"),
    )
    op.create_index("ix_meme_candidates_generation", "meme_caption_candidates", ["generation_id", "created_at"])
    op.create_index("ix_meme_candidates_phrase", "meme_caption_candidates", ["phrase_hash", "created_at"])

    op.create_table(
        "generated_memes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("generation_id", sa.String(length=36), sa.ForeignKey("meme_generations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), sa.ForeignKey("meme_caption_candidates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("asset_id", sa.String(length=36), sa.ForeignKey("media_assets.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("server_id", sa.Integer(), sa.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("experience_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_key", sa.String(length=64), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("captions_snapshot", sa.JSON(), nullable=False),
        sa.Column("target_player_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lore_references", sa.JSON(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False, server_default="1200"),
        sa.Column("height", sa.Integer(), nullable=False, server_default="1200"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_generated_memes_server_created", "generated_memes", ["server_id", "created_at"])
    op.create_index("ix_generated_memes_session_created", "generated_memes", ["session_id", "created_at"])

    op.create_table(
        "meme_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("meme_id", sa.String(length=36), sa.ForeignKey("generated_memes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feedback_type", sa.String(length=24), nullable=False),
        sa.Column("details", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("meme_id", "user_id", name="uq_meme_feedback_user"),
    )


def downgrade() -> None:
    op.drop_table("meme_feedback")
    op.drop_index("ix_generated_memes_session_created", table_name="generated_memes")
    op.drop_index("ix_generated_memes_server_created", table_name="generated_memes")
    op.drop_table("generated_memes")
    op.drop_index("ix_meme_candidates_phrase", table_name="meme_caption_candidates")
    op.drop_index("ix_meme_candidates_generation", table_name="meme_caption_candidates")
    op.drop_table("meme_caption_candidates")
    op.drop_index("ix_meme_generations_status", table_name="meme_generations")
    op.drop_index("ix_meme_generations_server_created", table_name="meme_generations")
    op.drop_table("meme_generations")
    op.drop_table("meme_player_preferences")

