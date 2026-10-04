"""Persist seat takeover history for snapshots and PGN exports."""

import sqlalchemy as sa
from alembic import op

revision = "0008_seat_history"
down_revision = "0007_human_draws"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("seat_history", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("matches", "seat_history")
