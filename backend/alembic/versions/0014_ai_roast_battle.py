"""Add consent-first AI Roast Battle state."""
from alembic import op
import sqlalchemy as sa

revision = "0014_ai_roast_battle"
down_revision = "0013_highlight_generator"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("roast_profiles",
        sa.Column("server_id", sa.Integer(), sa.ForeignKey("servers.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("roast_enabled", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("maximum_intensity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("allowed_topics", sa.JSON(), nullable=False), sa.Column("allow_party_lore", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("allow_highlights", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("allow_recent_failures", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("blocked_terms", sa.JSON(), nullable=False), sa.Column("consent_version", sa.Integer(), nullable=False, server_default="1"), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("maximum_intensity >= 0 AND maximum_intensity <= 2", name="ck_roast_profile_intensity"))
    op.create_table("roast_session_players",
        sa.Column("session_id", sa.String(36), sa.ForeignKey("experience_sessions.id", ondelete="CASCADE"), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("seat", sa.Integer(), nullable=False), sa.Column("consent_state", sa.String(16), nullable=False, server_default="pending"), sa.Column("consent_version", sa.Integer(), nullable=False), sa.Column("profile_snapshot", sa.JSON(), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("total_score", sa.Float(), nullable=False, server_default="0"), sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True), sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("session_id", "seat", name="uq_roast_session_player_seat"))
    op.create_table("roast_rounds",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("session_id", sa.String(36), sa.ForeignKey("experience_sessions.id", ondelete="CASCADE"), nullable=False), sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("target_player_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("effective_intensity", sa.Integer(), nullable=False), sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="generating"), sa.Column("selected_candidate_id", sa.String(36), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("session_id", "round_number", name="uq_roast_round_number"))
    op.create_index("ix_roast_rounds_session", "roast_rounds", ["session_id", "round_number"])
    op.create_table("roast_candidates",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("round_id", sa.String(36), sa.ForeignKey("roast_rounds.id", ondelete="CASCADE"), nullable=False, unique=True), sa.Column("target_player_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("roast_text", sa.String(280), nullable=False), sa.Column("phrase_hash", sa.String(64), nullable=False), sa.Column("angle", sa.String(40), nullable=False), sa.Column("intensity", sa.Integer(), nullable=False), sa.Column("source_lore_ids", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False), sa.Column("quality_score", sa.Float(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("displayed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("intensity >= 0 AND intensity <= 2", name="ck_roast_candidate_intensity"), sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_roast_candidate_confidence"))
    op.create_index("ix_roast_candidates_target_created", "roast_candidates", ["target_player_id", "created_at"])
    op.create_table("roast_votes",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("candidate_id", sa.String(36), sa.ForeignKey("roast_candidates.id", ondelete="CASCADE"), nullable=False), sa.Column("voter_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("vote_type", sa.String(12), nullable=False), sa.Column("is_target_vote", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("score_contribution", sa.Float(), nullable=False, server_default="0"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("candidate_id", "voter_id", name="uq_roast_vote_user"))

def downgrade() -> None:
    op.drop_table("roast_votes"); op.drop_index("ix_roast_candidates_target_created", table_name="roast_candidates"); op.drop_table("roast_candidates"); op.drop_index("ix_roast_rounds_session", table_name="roast_rounds"); op.drop_table("roast_rounds"); op.drop_table("roast_session_players"); op.drop_table("roast_profiles")
