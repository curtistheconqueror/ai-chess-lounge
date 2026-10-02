"""Add normalized player seats and safe per-move metadata.

Revision ID: 0004_player_seats
Revises: 0003_concurrency_guards
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_player_seats"
down_revision: str | None = "0003_concurrency_guards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("white_player", sa.JSON(), nullable=True))
    op.add_column("matches", sa.Column("black_player", sa.JSON(), nullable=True))
    op.add_column("moves", sa.Column("player_metadata", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("moves", "player_metadata")
    op.drop_column("matches", "black_player")
    op.drop_column("matches", "white_player")
