"""Create durable matches, moves, and append-only events.

Revision ID: 0001_durable_matches
Revises:
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_durable_matches"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "matches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("lifecycle", sa.String(length=24), nullable=False),
        sa.Column("opponent", sa.String(length=24), nullable=False),
        sa.Column("stockfish_elo", sa.Integer(), nullable=False),
        sa.Column("engine_move_time_ms", sa.Integer(), nullable=False),
        sa.Column("initial_fen", sa.Text(), nullable=False),
        sa.Column("current_fen", sa.Text(), nullable=False),
        sa.Column("position_version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("resigned_by", sa.String(length=5), nullable=True),
        sa.Column("adjudicated_result", sa.String(length=7), nullable=True),
        sa.Column("engine_summary", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "match_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("match_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("position_version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "sequence", name="uq_events_match_sequence"),
    )
    op.create_index("ix_events_match_sequence", "match_events", ["match_id", "sequence"])
    op.create_table(
        "moves",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("match_id", sa.String(length=36), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("ply", sa.Integer(), nullable=False),
        sa.Column("uci", sa.String(length=5), nullable=False),
        sa.Column("san", sa.String(length=16), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("fen", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "generation", "ply", name="uq_moves_match_generation_ply"),
    )
    op.create_index("ix_moves_match_generation", "moves", ["match_id", "generation"])


def downgrade() -> None:
    op.drop_index("ix_moves_match_generation", table_name="moves")
    op.drop_table("moves")
    op.drop_index("ix_events_match_sequence", table_name="match_events")
    op.drop_table("match_events")
    op.drop_table("matches")
