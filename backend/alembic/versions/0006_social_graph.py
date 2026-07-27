"""Add friendships and private Matrix conversations."""

from alembic import op
import sqlalchemy as sa


revision = "0006_social_graph"
down_revision = "0005_chance_games"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "friendships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_low_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_high_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requested_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("matrix_room_id", sa.String(length=255), nullable=True),
        sa.Column(
            "matrix_owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("user_low_id < user_high_id", name="ck_friendship_order"),
        sa.UniqueConstraint("user_low_id", "user_high_id", name="uq_friendship_pair"),
        sa.UniqueConstraint("matrix_room_id", name="uq_friendships_matrix_room_id"),
    )
    op.create_index("ix_friendships_status", "friendships", ["status"])


def downgrade() -> None:
    op.drop_index("ix_friendships_status", table_name="friendships")
    op.drop_table("friendships")
