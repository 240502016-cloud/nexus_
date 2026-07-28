"""Add persistent server invitations."""

from alembic import op
import sqlalchemy as sa


revision = "0007_server_invites"
down_revision = "0006_social_graph"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "server_invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "server_id",
            sa.Integer(),
            sa.ForeignKey("servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "inviter_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invitee_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("server_id", "invitee_id", name="uq_server_invite_target"),
    )
    op.create_index(
        "ix_server_invites_invitee_status",
        "server_invites",
        ["invitee_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_server_invites_invitee_status", table_name="server_invites")
    op.drop_table("server_invites")
