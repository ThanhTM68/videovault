"""Execution event identity and last-known missing media state."""

import sqlalchemy as sa
from alembic import op

revision = "0003_library"
down_revision = "0002_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("downloads", sa.Column("attempt_number", sa.Integer(), nullable=True))
    op.create_index(
        "ix_downloads_job_attempt", "downloads", ["job_id", "attempt_number"], unique=True
    )
    op.add_column("media_files", sa.Column("missing_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("media_files", "missing_at")
    op.drop_index("ix_downloads_job_attempt", table_name="downloads")
    op.drop_column("downloads", "attempt_number")
