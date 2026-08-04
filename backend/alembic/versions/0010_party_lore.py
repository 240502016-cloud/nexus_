"""Add consent-first Party Lore records."""

from alembic import op
import sqlalchemy as sa


revision = "0010_party_lore"
down_revision = "0009_platform_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lore_candidates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "server_id",
            sa.Integer(),
            sa.ForeignKey("servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "submitted_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False, server_default="moment"),
        sa.Column("sensitivity", sa.String(length=16), nullable=False, server_default="low"),
        sa.Column("allowed_modules", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "server_id",
            "submitted_by_id",
            "idempotency_key",
            name="uq_lore_candidate_idempotency",
        ),
    )
    op.create_index(
        "ix_lore_candidates_server_status",
        "lore_candidates",
        ["server_id", "status", "created_at"],
    )

    op.create_table(
        "lore_candidate_participants",
        sa.Column(
            "candidate_id",
            sa.String(length=36),
            sa.ForeignKey("lore_candidates.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("decision", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_lore_candidate_participants_user",
        "lore_candidate_participants",
        ["user_id", "decision"],
    )

    op.create_table(
        "lore_entries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.String(length=36),
            sa.ForeignKey("lore_candidates.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "server_id",
            sa.Integer(),
            sa.ForeignKey("servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("sensitivity", sa.String(length=16), nullable=False),
        sa.Column("allowed_modules", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_lore_entries_retrieve",
        "lore_entries",
        ["server_id", "status", "sensitivity"],
    )
    op.create_index(
        "ix_lore_entries_category",
        "lore_entries",
        ["server_id", "category"],
    )

    op.create_table(
        "lore_participants",
        sa.Column(
            "lore_id",
            sa.String(length=36),
            sa.ForeignKey("lore_entries.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("consent_state", sa.String(length=16), nullable=False, server_default="confirmed"),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_lore_participants_user",
        "lore_participants",
        ["user_id", "consent_state"],
    )

    op.create_table(
        "lore_evidence",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "lore_id",
            sa.String(length=36),
            sa.ForeignKey("lore_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_lore_evidence_entry", "lore_evidence", ["lore_id"])

    op.create_table(
        "lore_usage",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column(
            "lore_id",
            sa.String(length=36),
            sa.ForeignKey("lore_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "server_id",
            sa.Integer(),
            sa.ForeignKey("servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("module", sa.String(length=32), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("request_id", "lore_id", name="uq_lore_usage_request_entry"),
    )
    op.create_index(
        "ix_lore_usage_server_created", "lore_usage", ["server_id", "created_at"]
    )
    op.create_index("ix_lore_usage_entry_created", "lore_usage", ["lore_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_lore_usage_entry_created", table_name="lore_usage")
    op.drop_index("ix_lore_usage_server_created", table_name="lore_usage")
    op.drop_table("lore_usage")
    op.drop_index("ix_lore_evidence_entry", table_name="lore_evidence")
    op.drop_table("lore_evidence")
    op.drop_index("ix_lore_participants_user", table_name="lore_participants")
    op.drop_table("lore_participants")
    op.drop_index("ix_lore_entries_category", table_name="lore_entries")
    op.drop_index("ix_lore_entries_retrieve", table_name="lore_entries")
    op.drop_table("lore_entries")
    op.drop_index(
        "ix_lore_candidate_participants_user", table_name="lore_candidate_participants"
    )
    op.drop_table("lore_candidate_participants")
    op.drop_index("ix_lore_candidates_server_status", table_name="lore_candidates")
    op.drop_table("lore_candidates")
