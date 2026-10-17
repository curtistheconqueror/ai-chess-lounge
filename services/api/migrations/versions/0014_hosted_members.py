"""Hosted invite list, match ownership and per-player table settings (ADR0043)."""

import sqlalchemy as sa
from alembic import op

revision = "0014_hosted_members"
down_revision = "0013_table_settings"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("matches") as batch:
        batch.add_column(sa.Column("owner_id", sa.String(64), nullable=True))
        batch.create_index("ix_matches_owner_id", ["owner_id"])
    with op.batch_alter_table("table_settings") as batch:
        batch.alter_column("id", existing_type=sa.String(32), type_=sa.String(64))
    op.create_table(
        "lounge_members",
        sa.Column("email", sa.String(254), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("invited_by", sa.String(254), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    if op.get_bind().dialect.name == "postgresql":
        # On Supabase, tables in "public" are reachable through its REST API unless row
        # level security is on. The Lounge connects as the database owner, so RLS with
        # no policies blocks only that API path. Match the existing tables.
        for table in ("table_settings", "lounge_members"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade():
    op.drop_table("lounge_members")
    with op.batch_alter_table("table_settings") as batch:
        batch.alter_column("id", existing_type=sa.String(64), type_=sa.String(32))
    with op.batch_alter_table("matches") as batch:
        batch.drop_index("ix_matches_owner_id")
        batch.drop_column("owner_id")
