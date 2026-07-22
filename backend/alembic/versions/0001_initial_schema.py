"""Adopt the initial Nexus application schema under Alembic control.

This revision deliberately uses SQLAlchemy metadata rather than embedding a second copy of
the table definitions. It is safe for an existing create_all database because create_all is
idempotent; Alembic's version table records that the schema is now migration-managed. Future
schema changes must be explicit revisions and must not be added to this baseline.
"""

from alembic import op

from app.database import Base
from app.core import models as core_models  # noqa: F401
from app.services.ollama import models as ollama_models  # noqa: F401


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = [table for table in Base.metadata.sorted_tables if table.name not in {"ai_jobs", "ai_bot_jobs"}]
    Base.metadata.create_all(bind=op.get_bind(), tables=tables)


def downgrade() -> None:
    tables = [table for table in Base.metadata.sorted_tables if table.name not in {"ai_jobs", "ai_bot_jobs"}]
    Base.metadata.drop_all(bind=op.get_bind(), tables=tables)
