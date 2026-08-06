"""Add deterministic AI Board Game state and action ledger."""
from alembic import op
import sqlalchemy as sa

revision = "0016_ai_board_game"
down_revision = "0015_user_auth_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "board_game_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("experience_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("public_state", sa.JSON(), nullable=False),
        sa.Column("engine_state", sa.JSON(), nullable=False),
        sa.Column("rng_commitment", sa.String(64), nullable=False),
        sa.Column("rng_counter", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "revision", name="uq_board_game_state_revision"),
    )
    op.create_index("ix_board_game_state_current", "board_game_states", ["session_id", "is_current"])
    op.create_table(
        "board_game_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("experience_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("action_id", sa.String(80), nullable=False),
        sa.Column("expected_revision", sa.Integer(), nullable=False),
        sa.Column("applied_revision", sa.Integer(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "actor_id", "idempotency_key", name="uq_board_game_action_idempotency"),
    )
    op.create_index("ix_board_game_actions_session_revision", "board_game_actions", ["session_id", "applied_revision"])


def downgrade() -> None:
    op.drop_index("ix_board_game_actions_session_revision", table_name="board_game_actions")
    op.drop_table("board_game_actions")
    op.drop_index("ix_board_game_state_current", table_name="board_game_states")
    op.drop_table("board_game_states")
