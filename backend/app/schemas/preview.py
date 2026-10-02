from pydantic import Field, ValidationError, field_validator

from app.core.errors import AppError
from app.models.enums import Platform
from app.services.downloader.models import DomainModel
from app.services.queue.models import DownloadPayload


class ResolveRequest(DomainModel):
    url: str = Field(max_length=8192)

    @field_validator("url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        try:
            return DownloadPayload(url=value, max_height=1080).url
        except (AppError, ValidationError):
            raise ValueError("Invalid video URL") from None


class VideoPreview(DomainModel):
    platform: Platform
    platform_video_id: str
    canonical_url: str
    title: str | None
    creator: str | None
    duration_seconds: float | None
    width: int | None
    height: int | None
    thumbnail_url: str | None
