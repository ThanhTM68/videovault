"""Initial V1 schema

Revision ID: 0001_v1
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_v1"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collections",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collections")),
    )
    op.create_table(
        "creators",
        sa.Column(
            "platform",
            sa.Enum(
                "youtube",
                "tiktok",
                "douyin",
                "instagram",
                "facebook",
                name="platform",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("platform_creator_id", sa.String(length=255), nullable=True),
        sa.Column("handle", sa.String(length=255), nullable=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_creators")),
        sa.UniqueConstraint("platform", "platform_creator_id", name=op.f("uq_creators_platform")),
    )
    op.create_table(
        "jobs",
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "resolving",
                "downloading",
                "processing",
                "uploading",
                "completed",
                "failed",
                "cancelled",
                "skipped_duplicate",
                name="job_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("progress_percent", sa.Float(), nullable=False),
        sa.Column("current_step", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("attempt_count >= 0", name=op.f("ck_jobs_attempts_nonnegative")),
        sa.CheckConstraint("length(trim(type)) > 0", name=op.f("ck_jobs_type_nonempty")),
        sa.CheckConstraint("max_attempts >= 1", name=op.f("ck_jobs_max_attempts_positive")),
        sa.CheckConstraint(
            "progress_percent BETWEEN 0 AND 100", name=op.f("ck_jobs_progress_range")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_table(
        "storage_accounts",
        sa.Column(
            "provider",
            sa.Enum(
                "local",
                "google_drive",
                name="storage_provider",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("provider_account_id", sa.Text(), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_storage_accounts")),
    )
    op.create_table(
        "tags",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tags")),
        sa.UniqueConstraint("name", name=op.f("uq_tags_name")),
    )
    op.create_table(
        "videos",
        sa.Column(
            "platform",
            sa.Enum(
                "youtube",
                "tiktok",
                "douyin",
                "instagram",
                "facebook",
                name="platform",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("platform_video_id", sa.String(length=255), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("creator_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("upload_date", sa.Date(), nullable=True),
        sa.Column("view_count", sa.BigInteger(), nullable=True),
        sa.Column("like_count", sa.BigInteger(), nullable=True),
        sa.Column("comment_count", sa.BigInteger(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("fps", sa.Float(), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("discovered_at", sa.DateTime(), nullable=False),
        sa.Column("last_refreshed_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.CheckConstraint("comment_count >= 0", name=op.f("ck_videos_comments_nonnegative")),
        sa.CheckConstraint("duration_seconds >= 0", name=op.f("ck_videos_duration_nonnegative")),
        sa.CheckConstraint("fps > 0", name=op.f("ck_videos_fps_positive")),
        sa.CheckConstraint(
            "length(trim(platform_video_id)) > 0", name=op.f("ck_videos_video_identity_nonempty")
        ),
        sa.CheckConstraint("like_count >= 0", name=op.f("ck_videos_likes_nonnegative")),
        sa.CheckConstraint("view_count >= 0", name=op.f("ck_videos_views_nonnegative")),
        sa.CheckConstraint("width > 0 AND height > 0", name=op.f("ck_videos_dimensions_positive")),
        sa.ForeignKeyConstraint(
            ["creator_id"],
            ["creators.id"],
            name=op.f("fk_videos_creator_id_creators"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_videos")),
        sa.UniqueConstraint("platform", "platform_video_id", name=op.f("uq_videos_platform")),
    )
    with op.batch_alter_table("videos", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_videos_creator_id"), ["creator_id"], unique=False)

    op.create_table(
        "collection_videos",
        sa.Column("collection_id", sa.String(length=36), nullable=False),
        sa.Column("video_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["collections.id"],
            name=op.f("fk_collection_videos_collection_id_collections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["video_id"],
            ["videos.id"],
            name=op.f("fk_collection_videos_video_id_videos"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("collection_id", "video_id", name=op.f("pk_collection_videos")),
    )
    with op.batch_alter_table("collection_videos", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_collection_videos_video_id"), ["video_id"], unique=False
        )

    op.create_table(
        "downloads",
        sa.Column("video_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("requested_quality", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "resolving",
                "downloading",
                "processing",
                "uploading",
                "completed",
                "failed",
                "cancelled",
                "skipped_duplicate",
                name="download_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("failure_code", sa.Text(), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("forced", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_downloads_job_id_jobs"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["video_id"],
            ["videos.id"],
            name=op.f("fk_downloads_video_id_videos"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_downloads")),
    )
    with op.batch_alter_table("downloads", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_downloads_job_id"), ["job_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_downloads_video_id"), ["video_id"], unique=False)

    op.create_table(
        "video_tags",
        sa.Column("video_id", sa.String(length=36), nullable=False),
        sa.Column("tag_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["tags.id"], name=op.f("fk_video_tags_tag_id_tags"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["video_id"],
            ["videos.id"],
            name=op.f("fk_video_tags_video_id_videos"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("video_id", "tag_id", name=op.f("pk_video_tags")),
    )
    with op.batch_alter_table("video_tags", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_video_tags_tag_id"), ["tag_id"], unique=False)

    op.create_table(
        "media_files",
        sa.Column("video_id", sa.String(length=36), nullable=False),
        sa.Column("download_id", sa.String(length=36), nullable=True),
        sa.Column(
            "storage_provider",
            sa.Enum(
                "local",
                "google_drive",
                name="storage_provider",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column(
            "kind",
            sa.Enum(
                "original",
                "edited",
                "thumbnail",
                "audio",
                name="media_kind",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("exists_last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "duration_seconds >= 0", name=op.f("ck_media_files_duration_nonnegative")
        ),
        sa.CheckConstraint("size_bytes >= 0", name=op.f("ck_media_files_size_nonnegative")),
        sa.CheckConstraint(
            "width > 0 AND height > 0", name=op.f("ck_media_files_dimensions_positive")
        ),
        sa.ForeignKeyConstraint(
            ["download_id"],
            ["downloads.id"],
            name=op.f("fk_media_files_download_id_downloads"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["video_id"],
            ["videos.id"],
            name=op.f("fk_media_files_video_id_videos"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_files")),
    )
    with op.batch_alter_table("media_files", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_media_files_download_id"), ["download_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_media_files_video_id"), ["video_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("media_files", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_media_files_video_id"))
        batch_op.drop_index(batch_op.f("ix_media_files_download_id"))

    op.drop_table("media_files")
    with op.batch_alter_table("video_tags", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_video_tags_tag_id"))

    op.drop_table("video_tags")
    with op.batch_alter_table("downloads", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_downloads_video_id"))
        batch_op.drop_index(batch_op.f("ix_downloads_job_id"))

    op.drop_table("downloads")
    with op.batch_alter_table("collection_videos", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_collection_videos_video_id"))

    op.drop_table("collection_videos")
    with op.batch_alter_table("videos", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_videos_creator_id"))

    op.drop_table("videos")
    op.drop_table("tags")
    op.drop_table("storage_accounts")
    op.drop_table("jobs")
    op.drop_table("creators")
    op.drop_table("collections")
