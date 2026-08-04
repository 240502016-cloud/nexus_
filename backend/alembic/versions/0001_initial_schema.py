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

# Freeze the historical baseline to an allow-list. An exclude-list makes revision 0001
# depend on today's metadata and causes new module tables to collide with their own
# migrations during a fresh installation.
_BASELINE_TABLES = {
    "ai_conversations",
    "ai_messages",
    "ai_token_usage",
    "bot_server_links",
    "bots",
    "channels",
    "plugins",
    "roles",
    "server_members",
    "servers",
    "user_roles",
    "users",
}


def upgrade() -> None:
    # Bu migration güncel ORM metadata'sını kullandığından, sonraki revision'larda eklenen
    # tablolar burada açıkça dışarıda tutulmalıdır. Aksi halde temiz kurulumda aynı tabloyu
    # ilgili revision ikinci kez oluşturmaya çalışır.
    tables = [
        table for table in Base.metadata.sorted_tables if table.name in _BASELINE_TABLES
    ]
    Base.metadata.create_all(bind=op.get_bind(), tables=tables)


def downgrade() -> None:
    tables = [
        table for table in Base.metadata.sorted_tables if table.name in _BASELINE_TABLES
    ]
    Base.metadata.drop_all(bind=op.get_bind(), tables=tables)
