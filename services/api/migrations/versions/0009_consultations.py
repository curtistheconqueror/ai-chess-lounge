"""Persist human consultation history."""

import sqlalchemy as sa
from alembic import op

revision = "0009_consultations"
down_revision = "0008_seat_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("consultations", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("matches", "consultations")
