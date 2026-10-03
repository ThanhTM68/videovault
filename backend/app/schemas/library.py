from datetime import date, datetime

from pydantic import Field, field_validator

from app.models.enums import DownloadStatus, Platform, StorageProvider
from app.services.downloader.models import DomainModel


class NamedItem(DomainModel):
    id: str
    name: str


class NameInput(DomainModel):
    name: str = Field(min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def clean(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Empty name")
        return value


class LibraryVideo(DomainModel):
    id: str
    platform: Platform
    platform_video_id: str
    title: str
    creator: str | None
    thumbnail_url: str | None
    duration_seconds: float | None
    upload_date: date | None
    view_count: int | None
    width: int | None
    height: int | None
    has_file: bool
    has_download_history: bool
    tags: list[NamedItem]
    collections: list[NamedItem]


class HistoryItem(DomainModel):
    id: str
    video_id: str
    title: str
    platform: Platform
    status: DownloadStatus
    forced: bool
    attempt_number: int | None
    job_id: str | None
    requested_quality: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failure_code: str | None
    failure_message: str | None


class FileSummary(DomainModel):
    id: str
    storage_provider: StorageProvider
    file_name: str
    size_bytes: int
    sha256: str | None
    container: str
    width: int | None
    height: int | None
    state: str


class VideoDetail(LibraryVideo):
    description: str
    history: list[HistoryItem]
    files: list[FileSummary]


class VideoPage(DomainModel):
    items: list[LibraryVideo]
    page: int
    page_size: int
    total: int


class HistoryPage(DomainModel):
    items: list[HistoryItem]
    page: int
    page_size: int
    total: int
