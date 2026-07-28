"""Add shareable server join codes."""

from alembic import op
import sqlalchemy as sa


revision = "0008_server_join_codes"
down_revision = "0007_server_invites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "server_join_codes",
        sa.Column(
            "server_id",
            sa.Integer(),
            sa.ForeignKey("servers.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_server_join_codes_code",
        "server_join_codes",
        ["code"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_server_join_codes_code", table_name="server_join_codes")
    op.drop_table("server_join_codes")
