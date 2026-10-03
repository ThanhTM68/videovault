import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, field_validator

from app.models import Job
from app.models.enums import JobStatus, StorageProvider
from app.services.downloader.models import DomainModel
from app.services.downloader.platform import validate_video_url


class DownloadPayload(DomainModel):
    url: str = Field(max_length=8192)
    max_height: int = Field(ge=1, le=1080, strict=True)
    preferred_container: Literal["mp4", "mkv", "webm"] = "mp4"
    audio_enabled: bool = Field(default=True, strict=True)
    force: bool = Field(default=False, strict=True)
    storage_target: StorageProvider = StorageProvider.LOCAL

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlsplit(validate_video_url(value))
        identity = [
            (key, value)
            for key, value in parse_qsl(parsed.query)
            if key in {"v", "video_id", "id", "story_fbid"}
        ]
        if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,512}", value) for _, value in identity):
            raise ValueError("Invalid URL identity")
        # Persist identity only, never tracking/authentication query options.
        return urlunsplit(parsed._replace(query=urlencode(identity), fragment=""))


class JobError(DomainModel):
    code: str
    message: str


class JobView(DomainModel):
    id: str
    type: str
    status: JobStatus
    progress_percent: float
    current_step: str | None
    attempt_count: int
    max_attempts: int
    created_at: datetime
    started_at: datetime | None
    heartbeat_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    cancel_requested_at: datetime | None
    error: JobError | None

    @classmethod
    def from_job(cls, job: Job) -> "JobView":
        fields = {name: getattr(job, name) for name in cls.model_fields if name != "error"}
        fields["error"] = (
            JobError(code=job.error_code, message=job.error_message or "Job failed")
            if job.error_code
            else None
        )
        return cls(**fields)


class JobPage(DomainModel):
    items: list[JobView]
    page: int
    page_size: int
    total: int


@dataclass(frozen=True)
class Claim:
    id: str
    attempt: int
    payload: dict[str, object]
