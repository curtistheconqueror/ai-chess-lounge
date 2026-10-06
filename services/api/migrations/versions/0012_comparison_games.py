"""Immutable per-generation comparison identities and transactional outcomes."""

import sqlalchemy as sa
from alembic import op

revision = "0012_comparison_games"
down_revision = "0011_experiment_queue"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "comparison_games",
        sa.Column(
            "match_id",
            sa.String(36),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("generation", sa.Integer(), primary_key=True),
        sa.Column("identity", sa.JSON(), nullable=False),
        sa.Column("outcome", sa.JSON(), nullable=False),
    )


def downgrade():
    op.drop_table("comparison_games")
