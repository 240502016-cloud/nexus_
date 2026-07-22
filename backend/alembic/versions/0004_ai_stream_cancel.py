"""Add persisted streaming output and cancellation state to AI jobs."""

from alembic import op
import sqlalchemy as sa


revision = "0004_ai_stream_cancel"
down_revision = "0003_ai_bot_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ``output_text`` is deliberately durable so API SSE clients can reconnect and
    # resume from the latest worker flush without requiring an in-memory broker.
    op.add_column("ai_jobs", sa.Column("output_text", sa.Text(), nullable=True))
    op.add_column(
        "ai_jobs",
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_ai_jobs_cancel_requested", "ai_jobs", ["cancel_requested"])


def downgrade() -> None:
    op.drop_index("ix_ai_jobs_cancel_requested", table_name="ai_jobs")
    op.drop_column("ai_jobs", "cancel_requested")
    op.drop_column("ai_jobs", "output_text")
