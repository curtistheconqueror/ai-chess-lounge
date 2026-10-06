"""Add durable experiment run and job queue."""

import sqlalchemy as sa
from alembic import op

revision = "0011_experiment_queue"
down_revision = "0010_experiments"
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table(
        "experiment_dispatch_lock", sa.Column("id", sa.Integer(), primary_key=True)
    )
    op.bulk_insert(table, [{"id": 1}])
    op.create_table(
        "experiment_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("experiment_id", sa.String(36), sa.ForeignKey("experiments.id"), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("concurrency", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "experiment_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("experiment_runs.id"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("lease_token", sa.String(120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.String(24), nullable=True),
        sa.UniqueConstraint("run_id", "number", name="uq_experiment_job_number"),
    )


def downgrade():
    op.drop_table("experiment_jobs")
    op.drop_table("experiment_runs")
    op.drop_table("experiment_dispatch_lock")
