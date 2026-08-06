"""Add encrypted Hidden Role Game state."""
from alembic import op
import sqlalchemy as sa

revision = "0017_hidden_role_game"
down_revision = "0016_ai_board_game"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("hidden_role_states", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("session_id", sa.String(36), sa.ForeignKey("experience_sessions.id", ondelete="CASCADE"), nullable=False), sa.Column("revision", sa.Integer(), nullable=False), sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("public_state", sa.JSON(), nullable=False), sa.Column("engine_ciphertext", sa.LargeBinary(), nullable=False), sa.Column("rng_commitment", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("session_id", "revision", name="uq_hidden_role_state_revision"))
    op.create_index("ix_hidden_role_state_current", "hidden_role_states", ["session_id", "is_current"])
    op.create_table("hidden_role_assignments", sa.Column("session_id", sa.String(36), sa.ForeignKey("experience_sessions.id", ondelete="CASCADE"), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True), sa.Column("encrypted_payload", sa.LargeBinary(), nullable=False), sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("hidden_role_claims", sa.Column("id", sa.String(36), primary_key=True), sa.Column("session_id", sa.String(36), sa.ForeignKey("experience_sessions.id", ondelete="CASCADE"), nullable=False), sa.Column("round_number", sa.Integer(), nullable=False), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("subject_option_id", sa.String(1), nullable=False), sa.Column("proposition", sa.String(24), nullable=False), sa.Column("flavor_text", sa.Text(), nullable=False), sa.Column("verdict", sa.String(16), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("session_id", "round_number", "user_id", name="uq_hidden_role_claim_round_user"))
    op.create_table("hidden_role_votes", sa.Column("id", sa.String(36), primary_key=True), sa.Column("session_id", sa.String(36), sa.ForeignKey("experience_sessions.id", ondelete="CASCADE"), nullable=False), sa.Column("round_number", sa.Integer(), nullable=False), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("encrypted_payload", sa.LargeBinary(), nullable=False), sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("session_id", "round_number", "user_id", name="uq_hidden_role_vote_round_user"))
    op.create_table("hidden_role_deductions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("session_id", sa.String(36), sa.ForeignKey("experience_sessions.id", ondelete="CASCADE"), nullable=False), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("encrypted_payload", sa.LargeBinary(), nullable=False), sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("session_id", "user_id", name="uq_hidden_role_deduction_user"))

def downgrade() -> None:
    op.drop_table("hidden_role_deductions"); op.drop_table("hidden_role_votes"); op.drop_table("hidden_role_claims"); op.drop_table("hidden_role_assignments"); op.drop_index("ix_hidden_role_state_current", table_name="hidden_role_states"); op.drop_table("hidden_role_states")
