"""Add one-time runner pairings and scoped runner sessions.

Revision ID: 0005_remote_runners
Revises: 0004_player_seats
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_remote_runners"
down_revision: str | None = "0004_player_seats"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runner_pairings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code_digest", sa.String(length=64), nullable=False),
        sa.Column("player", sa.JSON(), nullable=False),
        sa.Column("session_ttl_ms", sa.Integer(), nullable=False),
        sa.Column("webhook_url", sa.String(length=2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "runner_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pairing_id", sa.String(length=36), nullable=False),
        sa.Column("player_id", sa.String(length=120), nullable=False),
        sa.Column("player", sa.JSON(), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("issuer_digest", sa.String(length=64), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("webhook_url", sa.String(length=2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["pairing_id"],
            ["runner_pairings.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pairing_id", name="uq_runner_sessions_pairing"),
    )
    op.create_index(
        "ix_runner_sessions_player",
        "runner_sessions",
        ["player_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_runner_sessions_player", table_name="runner_sessions")
    op.drop_table("runner_sessions")
    op.drop_table("runner_pairings")
