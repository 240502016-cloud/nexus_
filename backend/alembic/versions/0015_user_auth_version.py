"""Invalidate old access tokens after a password change."""

from alembic import op
import sqlalchemy as sa


revision = "0015_user_auth_version"
down_revision = "0014_ai_roast_battle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Revision 0001 eski kurulumları metadata üzerinden sahiplenir. Temiz kurulumda güncel
    # metadata bu sütunu zaten oluşturabileceği için ekleme işlemi idempotent olmalıdır.
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
    if "auth_version" not in columns:
        op.add_column(
            "users",
            sa.Column("auth_version", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    op.drop_column("users", "auth_version")
