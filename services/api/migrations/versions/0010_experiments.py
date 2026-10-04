"""Persist immutable experiment plans."""

import sqlalchemy as sa
from alembic import op

revision = "0010_experiments"
down_revision = "0009_consultations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("experiments")
