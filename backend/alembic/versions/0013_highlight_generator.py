"""Add Highlight Generator recording and render state."""

from alembic import op
import sqlalchemy as sa


revision = "0013_highlight_generator"
down_revision = "0012_meme_generator"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "highlight_recordings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("server_id", sa.Integer(), sa.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("experience_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", sa.String(36), sa.ForeignKey("media_assets.id", ondelete="SET NULL"), unique=True, nullable=True),
        sa.Column("probe_job_id", sa.String(36), sa.ForeignKey("background_jobs.id", ondelete="SET NULL"), unique=True, nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("original_filename", sa.String(180), nullable=False),
        sa.Column("declared_mime_type", sa.String(80), nullable=False),
        sa.Column("declared_byte_size", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(300), unique=True, nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("video_codec", sa.String(40), nullable=True),
        sa.Column("audio_codec", sa.String(40), nullable=True),
        sa.Column("has_audio", sa.Boolean(), nullable=True),
        sa.Column("probe_payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="awaiting_upload"),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("probed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("declared_byte_size >= 1 AND declared_byte_size <= 1073741824", name="ck_highlight_recording_declared_size"),
        sa.CheckConstraint("byte_size IS NULL OR (byte_size >= 1 AND byte_size <= 1073741824)", name="ck_highlight_recording_size"),
        sa.CheckConstraint("duration_ms IS NULL OR (duration_ms >= 1 AND duration_ms <= 900000)", name="ck_highlight_recording_duration"),
        sa.UniqueConstraint("server_id", "uploaded_by_id", "idempotency_key", name="uq_highlight_recording_request"),
    )
    op.create_index("ix_highlight_recordings_server_created", "highlight_recordings", ["server_id", "created_at"])
    op.create_index("ix_highlight_recordings_status", "highlight_recordings", ["status", "created_at"])

    op.create_table(
        "highlight_markers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("recording_id", sa.String(36), sa.ForeignKey("highlight_recordings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("external_marker_id", sa.String(160), nullable=False),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("offset_ms", sa.Integer(), nullable=False),
        sa.Column("category_hint", sa.String(24), nullable=True),
        sa.Column("participant_player_ids", sa.JSON(), nullable=False),
        sa.Column("summary", sa.String(500), nullable=True),
        sa.Column("manual_priority", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("commentator_priority", sa.Float(), nullable=True),
        sa.Column("game_event_severity", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("offset_ms >= 0", name="ck_highlight_marker_offset"),
        sa.CheckConstraint("manual_priority >= 0 AND manual_priority <= 1", name="ck_highlight_marker_priority"),
        sa.UniqueConstraint("recording_id", "external_marker_id", name="uq_highlight_marker_external"),
    )
    op.create_index("ix_highlight_markers_timeline", "highlight_markers", ["recording_id", "offset_ms"])

    op.create_table(
        "highlight_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("recording_id", sa.String(36), sa.ForeignKey("highlight_recordings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("marker_id", sa.String(36), sa.ForeignKey("highlight_markers.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("anchor_ms", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("primary_category", sa.String(24), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("participant_player_ids", sa.JSON(), nullable=False),
        sa.Column("signal_scores", sa.JSON(), nullable=False),
        sa.Column("lore_candidate", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("meme_candidate", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(24), nullable=False, server_default="proposed"),
        sa.Column("analysis_version", sa.String(40), nullable=False, server_default="highlight-score-v1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("start_ms >= 0 AND end_ms > start_ms", name="ck_highlight_candidate_window"),
        sa.CheckConstraint("end_ms - start_ms <= 60000", name="ck_highlight_candidate_max_duration"),
        sa.CheckConstraint("score >= 0 AND score <= 1", name="ck_highlight_candidate_score"),
    )
    op.create_index("ix_highlight_candidates_recording", "highlight_candidates", ["recording_id", "score"])

    op.create_table(
        "rendered_highlights",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("candidate_id", sa.String(36), sa.ForeignKey("highlight_candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("server_id", sa.Integer(), sa.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("experience_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("render_job_id", sa.String(36), sa.ForeignKey("background_jobs.id", ondelete="SET NULL"), unique=True, nullable=True),
        sa.Column("video_asset_id", sa.String(36), sa.ForeignKey("media_assets.id", ondelete="SET NULL"), unique=True, nullable=True),
        sa.Column("thumbnail_asset_id", sa.String(36), sa.ForeignKey("media_assets.id", ondelete="SET NULL"), unique=True, nullable=True),
        sa.Column("variant", sa.String(24), nullable=False, server_default="landscape"),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("render_parameters", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("candidate_id", "variant", name="uq_rendered_highlight_variant"),
    )
    op.create_index("ix_rendered_highlights_server_created", "rendered_highlights", ["server_id", "created_at"])

    op.create_table(
        "highlight_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("highlight_id", sa.String(36), sa.ForeignKey("rendered_highlights.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feedback_type", sa.String(24), nullable=False),
        sa.Column("details", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("highlight_id", "user_id", name="uq_highlight_feedback_user"),
    )


def downgrade() -> None:
    op.drop_table("highlight_feedback")
    op.drop_index("ix_rendered_highlights_server_created", table_name="rendered_highlights")
    op.drop_table("rendered_highlights")
    op.drop_index("ix_highlight_candidates_recording", table_name="highlight_candidates")
    op.drop_table("highlight_candidates")
    op.drop_index("ix_highlight_markers_timeline", table_name="highlight_markers")
    op.drop_table("highlight_markers")
    op.drop_index("ix_highlight_recordings_status", table_name="highlight_recordings")
    op.drop_index("ix_highlight_recordings_server_created", table_name="highlight_recordings")
    op.drop_table("highlight_recordings")

