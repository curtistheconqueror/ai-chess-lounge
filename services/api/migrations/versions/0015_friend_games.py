"""Friend games: seat owners, first-move timers, presence and challenges."""

import sqlalchemy as sa
from alembic import op

revision = "0015_friend_games"
down_revision = "0014_hosted_members"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("matches") as batch:
        batch.add_column(sa.Column("white_user_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("black_user_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("first_move_window_ms", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("abort_reason", sa.String(48), nullable=True))
        batch.create_index("ix_matches_white_user_id", ["white_user_id"])
        batch.create_index("ix_matches_black_user_id", ["black_user_id"])
    with op.batch_alter_table("lounge_members") as batch:
        batch.add_column(sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "challenges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("challenger_id", sa.String(64), nullable=False),
        sa.Column("challenger_email", sa.String(254), nullable=False),
        sa.Column("opponent_email", sa.String(254), nullable=False),
        sa.Column("initial_time_ms", sa.Integer(), nullable=False),
        sa.Column("increment_ms", sa.Integer(), nullable=False),
        sa.Column("color", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("game_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_challenges_challenger", "challenges", ["challenger_id", "status"])
    op.create_index("ix_challenges_opponent", "challenges", ["opponent_email", "status"])
    if op.get_bind().dialect.name == "postgresql":
        # Keep Supabase's REST API closed to it, like every other Lounge table.
        op.execute("ALTER TABLE challenges ENABLE ROW LEVEL SECURITY")


def downgrade():
    op.drop_index("ix_challenges_opponent", table_name="challenges")
    op.drop_index("ix_challenges_challenger", table_name="challenges")
    op.drop_table("challenges")
    with op.batch_alter_table("lounge_members") as batch:
        batch.drop_column("last_seen_at")
    with op.batch_alter_table("matches") as batch:
        batch.drop_index("ix_matches_black_user_id")
        batch.drop_index("ix_matches_white_user_id")
        batch.drop_column("abort_reason")
        batch.drop_column("first_move_window_ms")
        batch.drop_column("black_user_id")
        batch.drop_column("white_user_id")
