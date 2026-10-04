"""Persist human draw claims separately from adjudication."""

import sqlalchemy as sa
from alembic import op

revision = "0007_human_draws"
down_revision = "0006_runner_trust"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("draw_reason", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("matches", "draw_reason")
