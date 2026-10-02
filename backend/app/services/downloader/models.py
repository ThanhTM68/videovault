from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from app.models.enums import Platform
from app.services.downloader.errors import InvalidVideoUrlError
from app.services.downloader.platform import validate_video_url


class DomainModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class VideoFormat(DomainModel):
    format_id: str
    extension: str | None = None
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    fps: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    video_codec: str | None = None
    audio_codec: str | None = None
    bitrate: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    audio_bitrate: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    has_drm: bool = False

    @property
    def has_video(self) -> bool:
        return self.video_codec not in {None, "none"}

    @property
    def has_audio(self) -> bool:
        return self.audio_codec not in {None, "none"}


class NormalizedVideo(DomainModel):
    platform: Platform
    platform_video_id: str = Field(min_length=1, max_length=512)
    canonical_url: str
    title: str | None = None
    description: str | None = None
    creator: str | None = None
    creator_id: str | None = None
    creator_url: str | None = None
    duration_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    upload_date: date | None = None
    view_count: int | None = Field(default=None, ge=0)
    like_count: int | None = Field(default=None, ge=0)
    comment_count: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    fps: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    thumbnail_url: str | None = None
    formats: tuple[VideoFormat, ...] = ()
    raw_metadata: dict[str, JsonValue] = Field(default_factory=dict)


class DownloadRequest(DomainModel):
    url: str
    max_height: int = Field(default=1080, ge=1, le=1080, strict=True)
    output_directory: Path
    preferred_container: Literal["mp4", "mkv", "webm"] = "mp4"
    audio_enabled: bool = Field(default=True, strict=True)

    @field_validator("url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        try:
            return validate_video_url(value)
        except InvalidVideoUrlError:
            raise ValueError("A valid HTTP or HTTPS video URL is required") from None


class FormatSelection(DomainModel):
    video: VideoFormat
    audio: VideoFormat | None = None


class ProgressPhase(StrEnum):
    RESOLVING = "resolving"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    VALIDATING = "validating"
    COMPLETED = "completed"


class ProgressEvent(DomainModel):
    phase: ProgressPhase
    percent: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    downloaded_bytes: int | None = Field(default=None, ge=0)
    total_bytes: int | None = Field(default=None, ge=0)
    speed: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    eta: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    message: str | None = None
