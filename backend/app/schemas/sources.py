from datetime import date
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from app.models.enums import Platform
from app.schemas.queue import DownloadOptions, SubmittedJob
from app.services.downloader.models import DomainModel

MAX_CANDIDATES = 100


class SourceCapabilities(DomainModel):
    list_profile_or_channel: bool
    sort_newest: bool
    sort_oldest: bool
    sort_views: bool
    filter_views: bool
    filter_date: bool
    filter_duration: bool


class SourceResolveRequest(DomainModel):
    url: str = Field(min_length=1, max_length=2048)
    n: int = Field(default=20, ge=1, le=MAX_CANDIDATES, strict=True)
    ordering: Literal["source", "newest", "oldest", "views"] = "source"
    min_views: int | None = Field(default=None, ge=0, strict=True)
    max_views: int | None = Field(default=None, ge=0, strict=True)
    date_from: date | None = None
    date_to: date | None = None
    min_duration: float | None = Field(default=None, ge=0, strict=True, allow_inf_nan=False)
    max_duration: float | None = Field(default=None, ge=0, strict=True, allow_inf_nan=False)

    @field_validator("date_from", "date_to", mode="before")
    @classmethod
    def iso_date(cls, value: object) -> object:
        if value is None or type(value) is date:
            return value
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError("Expected YYYY-MM-DD")
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError("Expected YYYY-MM-DD")
        return parsed

    @model_validator(mode="after")
    def valid_ranges(self) -> "SourceResolveRequest":
        for low, high in (
            (self.min_views, self.max_views),
            (self.date_from, self.date_to),
            (self.min_duration, self.max_duration),
        ):
            if low is not None and high is not None and low > high:
                raise ValueError("Invalid filter range")
        return self


class SourceSummary(DomainModel):
    platform: Platform
    source_type: Literal["channel_videos"] = "channel_videos"
    source_id: str | None
    display_name: str | None
    canonical_url: str
    capabilities: SourceCapabilities
    total_available: int | None = None


class BatchCandidate(DomainModel):
    platform: Platform
    platform_video_id: str
    canonical_url: str
    title: str | None
    creator: str | None
    thumbnail_url: str | None
    duration_seconds: float | None
    upload_date: date | None
    view_count: int | None
    has_download_history: bool = False
    has_file: bool = False


class PreviewStatistics(DomainModel):
    enumerated_count: int
    rejected_count: int
    duplicate_count: int
    metadata_unavailable_count: int
    filtered_count: int
    returned_count: int
    already_downloaded_count: int
    scan_limit: int = MAX_CANDIDATES


class SourcePreview(DomainModel):
    preview_id: str
    source: SourceSummary
    candidates: list[BatchCandidate]
    statistics: PreviewStatistics
    ordering: Literal["source", "newest", "oldest", "views"]


class BatchDownloadRequest(DownloadOptions):
    preview_id: str = Field(min_length=16, max_length=128)
    selected_ids: list[
        Annotated[str, Field(min_length=11, max_length=11, pattern=r"^[A-Za-z0-9_-]{11}$")]
    ] = Field(min_length=1, max_length=MAX_CANDIDATES)


class BatchOutcome(DomainModel):
    platform_video_id: str
    outcome: Literal["queued", "skipped_history", "skipped_duplicate_selection"]
    job_id: str | None = None


class BatchDownloadResult(DomainModel):
    jobs: list[SubmittedJob]
    outcomes: list[BatchOutcome]
    requested_count: int
    created_count: int
    skipped_history_count: int
    skipped_duplicate_selection_count: int
