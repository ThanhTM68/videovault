import logging
from collections.abc import Iterator, Mapping
from pathlib import Path

import yt_dlp
from yt_dlp.utils import (
    DownloadError,
    ExtractorError,
    GeoRestrictedError,
    PostProcessingError,
    UnavailableVideoError,
    UnsupportedError,
)

from app.models.enums import Platform
from app.services.downloader.base import AdapterCapabilities, ProgressCallback
from app.services.downloader.errors import (
    AuthenticationRequiredError,
    DownloaderError,
    DownloadFailedError,
    DownloadUnavailableError,
    MetadataResolveError,
    UnsupportedPlatformError,
)
from app.services.downloader.metadata import (
    check_single_video,
    integer,
    normalize_formats,
    normalize_metadata,
    number,
)
from app.services.downloader.models import (
    DownloadRequest,
    NormalizedVideo,
    ProgressEvent,
    ProgressPhase,
    VideoFormat,
)
from app.services.downloader.platform import detect_platform, validate_video_url
from app.services.downloader.progress import ProgressReporter
from app.services.downloader.selector import select_formats
from app.services.media.probe import require_tool

logger = logging.getLogger(__name__)
_EXTRACTOR_ERRORS = (
    DownloadError,
    ExtractorError,
    PostProcessingError,
    UnavailableVideoError,
    OSError,
)


class _QuietLogger:
    """Extractor messages may contain signed URLs, tokens and headers: discard them."""

    def debug(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass


def map_extractor_error(exc: Exception, *, downloading: bool = False) -> DownloaderError:
    # yt-dlp often wraps structured ExtractorError in DownloadError.
    underlying = getattr(exc, "exc_info", None)
    cause = underlying[1] if isinstance(underlying, tuple) and len(underlying) > 1 else exc
    message = f"{exc} {cause}".lower()  # Classification only; never returned or logged.
    if any(
        term in message
        for term in (
            "private",
            "sign in",
            "sign-in",
            "log in",
            "login",
            "cookies",
            "authentication",
            "members-only",
            "captcha",
        )
    ):
        return AuthenticationRequiredError()
    if isinstance(cause, UnsupportedError) or "unsupported url" in message:
        return UnsupportedPlatformError()
    if isinstance(cause, (UnavailableVideoError, GeoRestrictedError)) or any(
        term in message
        for term in (
            "unavailable",
            "removed",
            "not available",
            "drm",
            "no video formats",
            "requested format is not available",
        )
    ):
        return DownloadUnavailableError()
    if downloading or isinstance(cause, PostProcessingError):
        return DownloadFailedError()
    return MetadataResolveError()


def _options() -> dict[str, object]:
    return {
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "logger": _QuietLogger(),
        "noplaylist": True,
        "playlistend": 1,
        "extract_flat": "in_playlist",
        "cachedir": False,
        "socket_timeout": 30,
        "retries": 1,
        "fragment_retries": 1,
        "extractor_retries": 1,
        "ignoreerrors": False,
        "allow_unplayable_formats": False,
        "usenetrc": False,
        "overwrites": False,
    }


class YtDlpAdapter:
    """Generic single-video core; platform-specific policies belong to Phase 04."""

    capabilities = AdapterCapabilities()

    def resolve(self, url: str) -> NormalizedVideo:
        url = validate_video_url(url)
        platform = detect_platform(url)
        if not isinstance(platform, Platform):
            raise UnsupportedPlatformError()
        logger.info("Resolving video metadata (%s)", platform.value)
        try:
            with yt_dlp.YoutubeDL(_options()) as extractor:
                info = extractor.extract_info(url, download=False)
            if not isinstance(info, Mapping):
                raise MetadataResolveError()
            return normalize_metadata(info, platform, url)
        except _EXTRACTOR_ERRORS as exc:
            raise map_extractor_error(exc) from None

    def get_formats(self, video: NormalizedVideo) -> tuple[VideoFormat, ...]:
        return video.formats

    def download(
        self,
        video: NormalizedVideo,
        request: DownloadRequest,
        output_stem: Path,
        progress: ProgressCallback,
    ) -> Path:
        if detect_platform(request.url) != video.platform:
            raise UnsupportedPlatformError()
        if output_stem.parent.resolve() != request.output_directory.resolve():
            raise DownloadFailedError()
        reporter = ProgressReporter(progress)

        def select(context: Mapping[str, object]) -> Iterator[dict[str, object]]:
            raw = context.get("formats")
            selection = select_formats(
                normalize_formats(raw),
                request.max_height,
                request.preferred_container,
                request.audio_enabled,
            )
            assert isinstance(raw, (list, tuple))
            chosen = [selection.video] + ([selection.audio] if selection.audio is not None else [])
            streams = [
                next(
                    f
                    for f in raw
                    if isinstance(f, Mapping) and f.get("format_id") == choice.format_id
                )
                for choice in chosen
            ]
            if len(streams) == 1:
                yield streams[0]
            else:
                yield {
                    "format_id": "+".join(str(f["format_id"]) for f in streams),
                    "ext": request.preferred_container,
                    "requested_formats": streams,
                    "protocol": "+".join(str(f.get("protocol", "https")) for f in streams),
                }

        def hook(raw: Mapping[str, object]) -> None:
            if raw.get("status") == "finished":
                reporter(
                    ProgressEvent(
                        phase=ProgressPhase.PROCESSING, message="Processing downloaded streams"
                    )
                )
                return
            if raw.get("status") != "downloading":
                return
            downloaded = integer(raw.get("downloaded_bytes"))
            total = integer(raw.get("total_bytes")) or integer(raw.get("total_bytes_estimate"))
            percent = (
                min(100.0, 100 * downloaded / total) if downloaded is not None and total else None
            )
            reporter(
                ProgressEvent(
                    phase=ProgressPhase.DOWNLOADING,
                    percent=percent,
                    downloaded_bytes=downloaded,
                    total_bytes=total,
                    speed=number(raw.get("speed")),
                    eta=number(raw.get("eta")),
                )
            )

        def post_hook(raw: Mapping[str, object]) -> None:
            if raw.get("status") == "started":
                logger.info("Processing downloaded streams")
                reporter(ProgressEvent(phase=ProgressPhase.PROCESSING))

        options = _options()
        options.update(
            {
                "format": select,
                "outtmpl": str(output_stem).replace("%", "%%") + ".%(ext)s",
                "paths": {"home": str(output_stem.parent), "temp": str(output_stem.parent)},
                "ffmpeg_location": require_tool("ffmpeg"),
                "merge_output_format": request.preferred_container,
                "postprocessors": [
                    {"key": "FFmpegVideoRemuxer", "preferedformat": request.preferred_container}
                ],
                "progress_hooks": [hook],
                "postprocessor_hooks": [post_hook],
            }
        )
        logger.info("Starting temporary download (%s)", video.platform.value)
        try:
            with yt_dlp.YoutubeDL(options) as extractor:
                # Inspect first so playlist/private/live results never enter download.
                info = extractor.extract_info(request.url, download=False)
                if not isinstance(info, Mapping):
                    raise DownloadUnavailableError()
                check_single_video(info)
                if str(info.get("id")) != video.platform_video_id:
                    raise DownloadUnavailableError()
                result = extractor.process_ie_result(info, download=True)
                if result is None:
                    raise DownloadFailedError()
            # Fixed output template + remux target gives one expected final path.
            return output_stem.with_name(output_stem.name + "." + request.preferred_container)
        except _EXTRACTOR_ERRORS as exc:
            raise map_extractor_error(exc, downloading=True) from None
