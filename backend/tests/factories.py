from app.models import Download, MediaFile, Video
from app.models.enums import MediaKind, Platform, StorageProvider


def make_video(identity: str = "video-1", platform: Platform = Platform.YOUTUBE) -> Video:
    return Video(
        platform=platform, platform_video_id=identity, canonical_url="https://example.com/video"
    )


def make_media(video: Video, download: Download | None = None) -> MediaFile:
    return MediaFile(
        video_id=video.id,
        download_id=download.id if download else None,
        storage_provider=StorageProvider.LOCAL,
        storage_key="opaque/file-key",
        file_name="video.mp4",
        mime_type="video/mp4",
        size_bytes=123,
        kind=MediaKind.ORIGINAL,
    )
