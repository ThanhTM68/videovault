from collections.abc import Iterable

from app.services.downloader.errors import DownloadUnavailableError
from app.services.downloader.models import FormatSelection, VideoFormat


def select_formats(
    formats: Iterable[VideoFormat],
    max_height: int = 1080,
    preferred_container: str = "mp4",
    audio_enabled: bool = True,
) -> FormatSelection:
    """Known dimensions only; never silently fall back above the requested cap."""
    usable = [f for f in formats if not f.has_drm]
    audio = [f for f in usable if f.has_audio and not f.has_video]
    videos = [
        f
        for f in usable
        if f.has_video
        and f.height is not None
        and 0 < f.height <= max_height
        and ((f.has_audio or audio) if audio_enabled else not f.has_audio)
    ]
    if not videos:
        raise DownloadUnavailableError()
    video = max(
        videos,
        key=lambda f: (
            f.height or 0,
            f.fps or 0,
            f.bitrate or 0,
            f.extension == preferred_container,
            (f.video_codec or "").startswith(("avc", "h264")),
            f.has_audio,
            f.format_id,
        ),
    )
    selected_audio = None
    if audio_enabled and not video.has_audio:
        selected_audio = max(
            audio,
            key=lambda f: (
                f.audio_bitrate or f.bitrate or 0,
                (f.audio_codec or "").startswith(("mp4a", "aac"))
                if preferred_container == "mp4"
                else (f.audio_codec or "").startswith("opus"),
                f.format_id,
            ),
        )
    return FormatSelection(video=video, audio=selected_audio)
