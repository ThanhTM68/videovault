from enum import StrEnum

from sqlalchemy import Enum


class Platform(StrEnum):
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    DOUYIN = "douyin"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"


class DownloadStatus(StrEnum):
    QUEUED = "queued"
    RESOLVING = "resolving"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED_DUPLICATE = "skipped_duplicate"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RESOLVING = "resolving"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED_DUPLICATE = "skipped_duplicate"


class MediaKind(StrEnum):
    ORIGINAL = "original"
    EDITED = "edited"
    THUMBNAIL = "thumbnail"
    AUDIO = "audio"


class StorageProvider(StrEnum):
    LOCAL = "local"
    GOOGLE_DRIVE = "google_drive"


def enum_column(enum: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )
