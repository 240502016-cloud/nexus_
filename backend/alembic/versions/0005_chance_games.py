"""Add bot-plugin links and durable chance game state."""

from alembic import op
import sqlalchemy as sa


revision = "0005_chance_games"
down_revision = "0004_ai_stream_cancel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bot_plugin_links",
        sa.Column("bot_id", sa.Integer(), sa.ForeignKey("bots.id", ondelete="CASCADE"), primary_key=True),
        sa.Column(
            "plugin_name",
            sa.String(length=100),
            sa.ForeignKey("plugins.name", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "chance_game_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(length=16), nullable=False),
        sa.Column("game_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column(
            "server_id", sa.Integer(), sa.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "challenger_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "opponent_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("challenger_move", sa.String(length=16), nullable=True),
        sa.Column("opponent_move", sa.String(length=16), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_chance_game_sessions_public_id", "chance_game_sessions", ["public_id"], unique=True)
    op.create_index("ix_chance_game_open", "chance_game_sessions", ["server_id", "status"])
    op.create_index(
        "ix_chance_game_participants",
        "chance_game_sessions",
        ["challenger_id", "opponent_id"],
    )
    op.create_table(
        "chance_wheels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "server_id", sa.Integer(), sa.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("entries", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("channel_id", "owner_id", name="uq_chance_wheel_channel_owner"),
    )


def downgrade() -> None:
    op.drop_table("chance_wheels")
    op.drop_index("ix_chance_game_participants", table_name="chance_game_sessions")
    op.drop_index("ix_chance_game_open", table_name="chance_game_sessions")
    op.drop_index("ix_chance_game_sessions_public_id", table_name="chance_game_sessions")
    op.drop_table("chance_game_sessions")
    op.drop_table("bot_plugin_links")
