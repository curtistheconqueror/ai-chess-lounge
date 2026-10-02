"""Add idempotency records and durable turn leases.

Revision ID: 0003_concurrency_guards
Revises: 0002_authoritative_clocks
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_concurrency_guards"
down_revision: str | None = "0002_authoritative_clocks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("turn_lease_owner", sa.String(length=120)))
    op.add_column("matches", sa.Column("turn_lease_token", sa.String(length=36)))
    op.add_column("matches", sa.Column("turn_lease_position_version", sa.Integer()))
    op.add_column(
        "matches",
        sa.Column("turn_lease_acquired_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "matches",
        sa.Column("turn_lease_expires_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("match_id", sa.String(length=36), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("applied_revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "match_id",
            "operation",
            "idempotency_key",
            name="uq_idempotency_match_operation_key",
        ),
    )
    op.create_index(
        "ix_idempotency_match_created",
        "idempotency_keys",
        ["match_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_idempotency_match_created", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
    op.drop_column("matches", "turn_lease_expires_at")
    op.drop_column("matches", "turn_lease_acquired_at")
    op.drop_column("matches", "turn_lease_position_version")
    op.drop_column("matches", "turn_lease_token")
    op.drop_column("matches", "turn_lease_owner")
