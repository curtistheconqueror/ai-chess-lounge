"""Single shared next-match settings document for the one Lounge table."""

import sqlalchemy as sa
from alembic import op

revision = "0013_table_settings"
down_revision = "0012_comparison_games"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "table_settings",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("table_settings")
