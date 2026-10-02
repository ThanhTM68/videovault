from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import JsonValue
from sqlalchemy import JSON, CheckConstraint, Index, Text
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedMixin, IdentityMixin
from app.db.types import UTCDateTime
from app.models.enums import JobStatus, enum_column

if TYPE_CHECKING:
    from app.models.download import Download


class Job(IdentityMixin, CreatedMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_queue", "type", "status", "created_at"),
        CheckConstraint("length(trim(type)) > 0", name="type_nonempty"),
        CheckConstraint("progress_percent BETWEEN 0 AND 100", name="progress_range"),
        CheckConstraint("attempt_count >= 0", name="attempts_nonnegative"),
        CheckConstraint("max_attempts >= 1", name="max_attempts_positive"),
    )

    type: Mapped[str] = mapped_column(Text)
    status: Mapped[JobStatus] = mapped_column(
        enum_column(JobStatus, "job_status"), default=JobStatus.QUEUED
    )
    payload_json: Mapped[dict[str, JsonValue]] = mapped_column(
        MutableDict.as_mutable(JSON), default=dict
    )
    progress_percent: Mapped[float] = mapped_column(default=0)
    current_step: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=3)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    cancel_requested_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    downloads: Mapped[list["Download"]] = relationship(back_populates="job", passive_deletes="all")
