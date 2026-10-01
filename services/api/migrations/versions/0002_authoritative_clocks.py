"""Add server-authoritative match clocks.

Revision ID: 0002_authoritative_clocks
Revises: 0001_durable_matches
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_authoritative_clocks"
down_revision: str | None = "0001_durable_matches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column("initial_time_ms", sa.Integer(), server_default="300000", nullable=False),
    )
    op.add_column(
        "matches",
        sa.Column("increment_ms", sa.Integer(), server_default="2000", nullable=False),
    )
    op.add_column(
        "matches",
        sa.Column("white_remaining_ms", sa.Integer(), server_default="300000", nullable=False),
    )
    op.add_column(
        "matches",
        sa.Column("black_remaining_ms", sa.Integer(), server_default="300000", nullable=False),
    )
    op.add_column(
        "matches",
        sa.Column("turn_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("matches", sa.Column("timed_out_by", sa.String(length=5), nullable=True))
    op.add_column(
        "moves",
        sa.Column("white_remaining_ms", sa.Integer(), server_default="300000", nullable=False),
    )
    op.add_column(
        "moves",
        sa.Column("black_remaining_ms", sa.Integer(), server_default="300000", nullable=False),
    )
    op.execute(
        "UPDATE matches SET turn_started_at = CURRENT_TIMESTAMP "
        "WHERE lifecycle = 'running' AND turn_started_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("moves", "black_remaining_ms")
    op.drop_column("moves", "white_remaining_ms")
    op.drop_column("matches", "timed_out_by")
    op.drop_column("matches", "turn_started_at")
    op.drop_column("matches", "black_remaining_ms")
    op.drop_column("matches", "white_remaining_ms")
    op.drop_column("matches", "increment_ms")
    op.drop_column("matches", "initial_time_ms")
