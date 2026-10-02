"""Durable running cancellation and queue lookup index."""

import sqlalchemy as sa
from alembic import op

revision = "0002_queue"
down_revision = "0001_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("cancel_requested_at", sa.DateTime(), nullable=True))
    op.create_index("ix_jobs_queue", "jobs", ["type", "status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_jobs_queue", table_name="jobs")
    op.drop_column("jobs", "cancel_requested_at")
