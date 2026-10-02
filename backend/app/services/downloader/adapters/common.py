import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import SplitResult, urlsplit

from app.models.enums import Platform
from app.services.downloader.base import AdapterCapabilities, ExtractionPolicy, ProgressCallback
from app.services.downloader.errors import (
    DownloaderError,
    InvalidVideoUrlError,
    MetadataResolveError,
    UnsupportedPlatformError,
)
from app.services.downloader.metadata import (
    check_single_video,
    integer,
    normalize_metadata,
    number,
    safe_metadata_url,
    text,
)
from app.services.downloader.models import DownloadRequest, NormalizedVideo, VideoFormat
from app.services.downloader.platform import detect_platform, validate_video_url
from app.services.downloader.ytdlp import YtDlpAdapter

logger = logging.getLogger(__name__)


def string_id(value: object) -> str | None:
    """Preserve exact integer/string identities; never route them through float."""
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        if value.bit_length() > 1700:
            return None
        value = str(value)
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,512}", value):
        return value
    return None


def exact_count(value: object) -> int | None:
    if isinstance(value, str) and len(value) <= 128 and re.fullmatch(r"[0-9]+", value):
        return int(value)
    return integer(value)


def upload_date(info: Mapping[str, object]) -> str | None:
    raw = info.get("upload_date")
    if isinstance(raw, str) and re.fullmatch(r"[0-9]{8}", raw):
        try:
            datetime.strptime(raw, "%Y%m%d")
            return raw
        except ValueError:
            pass
    timestamp = number(info.get("timestamp"))
    if timestamp is not None:
        try:
            return datetime.fromtimestamp(timestamp, UTC).strftime("%Y%m%d")
        except (OverflowError, ValueError, OSError):
            pass
    return None


class PlatformAdapter:
    platform: Platform
    hosts: frozenset[str]
    extractor_names: tuple[str, ...]
    extractor_keys: tuple[str, ...]
    block_challenges = False
    capabilities = AdapterCapabilities()

    def __init__(self, core: YtDlpAdapter | None = None) -> None:
        self._core = core if core is not None else YtDlpAdapter()

    def _parse(self, url: str) -> SplitResult | None:
        parsed = urlsplit(validate_video_url(url))
        if parsed.hostname not in self.hosts or detect_platform(url) != self.platform:
            return None
        return parsed

    def can_handle(self, url: str) -> bool:
        raise NotImplementedError

    def extraction_url(self, url: str) -> str:
        url = validate_video_url(url)
        if not self.can_handle(url):
            raise UnsupportedPlatformError()
        return url

    def canonical_url(self, info: Mapping[str, object], url: str, identity: str) -> str:
        raise NotImplementedError

    def creator_fields(
        self, info: Mapping[str, object]
    ) -> tuple[str | None, str | None, str | None]:
        return (
            text(info.get("uploader") or info.get("channel")),
            string_id(info.get("uploader_id") or info.get("channel_id")),
            text(info.get("uploader_url") or info.get("channel_url")),
        )

    def normalize(self, info: Mapping[str, object], url: str) -> NormalizedVideo:
        self.extraction_url(url)
        check_single_video(info)
        source = info.get("extractor_key") or info.get("extractor")
        if not isinstance(source, str) or source.lower() not in {
            key.lower() for key in self.extractor_keys
        }:
            raise MetadataResolveError()
        webpage = info.get("webpage_url")
        if webpage is not None:
            try:
                if not isinstance(webpage, str) or not self.can_handle(webpage):
                    raise MetadataResolveError()
            except InvalidVideoUrlError:
                raise MetadataResolveError() from None
        identity = string_id(info.get("id"))
        if identity is None:
            raise MetadataResolveError()
        creator, creator_id, creator_url = self.creator_fields(info)
        # Copy the outer mapping: adapters never modify the extractor response.
        prepared = dict(info) | {
            "id": identity,
            "webpage_url": self.canonical_url(info, url, identity),
            "uploader": creator,
            "uploader_id": creator_id,
            "uploader_url": creator_url,
            "channel": None,
            "channel_id": None,
            "channel_url": None,
            "upload_date": upload_date(info),
        }
        safe_creator_url = safe_metadata_url(creator_url)
        prepared["uploader_url"] = (
            safe_creator_url
            if safe_creator_url is not None and detect_platform(safe_creator_url) == self.platform
            else None
        )
        for field in ("view_count", "like_count", "comment_count"):
            prepared[field] = exact_count(info.get(field))
        video = normalize_metadata(prepared, self.platform, url)
        candidates = [
            f for f in video.formats if f.has_video and not f.has_drm and f.height is not None
        ]
        if candidates:
            best = max(
                candidates, key=lambda f: (f.height or 0, f.width or 0, f.fps or 0, f.format_id)
            )
            video = video.model_copy(
                update={
                    "width": video.width if video.width is not None else best.width,
                    "height": video.height if video.height is not None else best.height,
                    "fps": video.fps if video.fps is not None else best.fps,
                }
            )
        return video

    def _policy(self) -> ExtractionPolicy:
        return ExtractionPolicy(self.normalize, self.extractor_names, self.block_challenges)

    def resolve(self, url: str) -> NormalizedVideo:
        url = self.extraction_url(url)
        try:
            video = self._core.resolve(url, policy=self._policy())
            logger.info("Platform metadata resolved (%s)", self.platform.value)
            return video
        except DownloaderError as exc:
            logger.warning("Platform resolve failed (%s, %s)", self.platform.value, exc.code)
            raise

    def get_formats(self, video: NormalizedVideo) -> tuple[VideoFormat, ...]:
        return self._core.get_formats(video)

    def download(
        self,
        video: NormalizedVideo,
        request: DownloadRequest,
        output_stem: Path,
        progress: ProgressCallback,
    ) -> Path:
        if video.platform != self.platform:
            raise UnsupportedPlatformError()
        execution = request.model_copy(update={"url": self.extraction_url(request.url)})
        return self._core.download(video, execution, output_stem, progress, policy=self._policy())
