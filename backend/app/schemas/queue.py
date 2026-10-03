from typing import Literal

from pydantic import Field, ValidationError, field_validator

from app.core.errors import AppError
from app.models.enums import StorageProvider
from app.services.downloader.models import DomainModel
from app.services.queue.models import DownloadPayload


class DownloadSubmission(DomainModel):
    urls: list[str] = Field(min_length=1, max_length=100)
    max_height: int | None = Field(default=None, ge=1, le=1080, strict=True)
    preferred_container: Literal["mp4", "mkv", "webm"] = "mp4"
    audio_enabled: bool = Field(default=True, strict=True)
    storage_target: StorageProvider | None = None
    force: bool = Field(default=False, strict=True)

    @field_validator("urls")
    @classmethod
    def valid_urls(cls, urls: list[str]) -> list[str]:
        try:
            return [DownloadPayload(url=url, max_height=1080).url for url in urls]
        except (AppError, ValidationError):
            raise ValueError("Invalid video URL") from None

    def payloads(
        self, default_height: int, default_target: StorageProvider = StorageProvider.LOCAL
    ) -> list[DownloadPayload]:
        return [
            DownloadPayload(
                url=url,
                max_height=self.max_height or default_height,
                preferred_container=self.preferred_container,
                audio_enabled=self.audio_enabled,
                force=self.force,
                storage_target=self.storage_target or default_target,
            )
            for url in self.urls
        ]


class SubmittedJob(DomainModel):
    id: str
    status: Literal["queued"] = "queued"


class SubmissionResult(DomainModel):
    jobs: list[SubmittedJob]


class QueueState(DomainModel):
    paused: bool
