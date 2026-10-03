"""Persist one-match runner grants and append-only trust events."""

import sqlalchemy as sa
from alembic import op

revision = "0006_runner_trust"
down_revision = "0005_remote_runners"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runner_match_grants",
        sa.Column(
            "session_id", sa.String(36), sa.ForeignKey("runner_sessions.id"), primary_key=True
        ),
        sa.Column("match_id", sa.String(120), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("color", sa.String(5), nullable=False),
        sa.Column("turns_dispatched", sa.Integer(), nullable=False),
        sa.Column("max_turns", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "runner_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("match_id", sa.String(120), nullable=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_runner_audit_events_session_id", "runner_audit_events", ["session_id"])


def downgrade() -> None:
    op.drop_table("runner_audit_events")
    op.drop_table("runner_match_grants")
