"""Queue AI bot commands instead of blocking the message API."""

from alembic import op
import sqlalchemy as sa


revision = "0003_ai_bot_jobs"
down_revision = "0002_ai_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_bot_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bot_id", sa.Integer(), sa.ForeignKey("bots.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("result_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_by", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_bot_jobs_status", "ai_bot_jobs", ["status"])
    op.create_index("ix_ai_bot_jobs_next_attempt_at", "ai_bot_jobs", ["next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_bot_jobs_next_attempt_at", table_name="ai_bot_jobs")
    op.drop_index("ix_ai_bot_jobs_status", table_name="ai_bot_jobs")
    op.drop_table("ai_bot_jobs")
