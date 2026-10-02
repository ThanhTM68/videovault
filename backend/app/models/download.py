from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedMixin, IdentityMixin
from app.db.types import UTCDateTime
from app.models.enums import DownloadStatus, MediaKind, StorageProvider, enum_column
from app.models.job import Job
from app.models.video import Video


class Download(IdentityMixin, CreatedMixin, Base):
    __tablename__ = "downloads"

    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="RESTRICT"), index=True)
    job_id: Mapped[str | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), index=True
    )
    requested_quality: Mapped[str] = mapped_column(Text, default="best")
    status: Mapped[DownloadStatus] = mapped_column(
        enum_column(DownloadStatus, "download_status"), default=DownloadStatus.QUEUED
    )
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    failure_code: Mapped[str | None] = mapped_column(Text)
    failure_message: Mapped[str | None] = mapped_column(Text)
    forced: Mapped[bool] = mapped_column(default=False)

    video: Mapped[Video] = relationship(back_populates="downloads")
    job: Mapped[Job | None] = relationship(back_populates="downloads")
    media_files: Mapped[list["MediaFile"]] = relationship(
        back_populates="download", passive_deletes="all"
    )


class MediaFile(IdentityMixin, CreatedMixin, Base):
    __tablename__ = "media_files"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="size_nonnegative"),
        CheckConstraint("width > 0 AND height > 0", name="dimensions_positive"),
        CheckConstraint("duration_seconds >= 0", name="duration_nonnegative"),
    )

    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="RESTRICT"), index=True)
    download_id: Mapped[str | None] = mapped_column(
        ForeignKey("downloads.id", ondelete="SET NULL"), index=True
    )
    storage_provider: Mapped[StorageProvider] = mapped_column(
        enum_column(StorageProvider, "storage_provider")
    )
    storage_key: Mapped[str] = mapped_column(Text)
    file_name: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(Text)
    width: Mapped[int | None]
    height: Mapped[int | None]
    duration_seconds: Mapped[float | None]
    kind: Mapped[MediaKind] = mapped_column(enum_column(MediaKind, "media_kind"))
    exists_last_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    video: Mapped[Video] = relationship(back_populates="media_files")
    download: Mapped[Download | None] = relationship(back_populates="media_files")
