"""Restricted metadata-only YouTube tab integration; no recursive video resolution."""

import time
from collections.abc import Mapping
from itertools import islice

import yt_dlp

from app.models.enums import Platform
from app.schemas.sources import MAX_CANDIDATES
from app.services.downloader.ytdlp import _options
from app.services.sources.errors import SourceError
from app.services.sources.urls import source_url


class _SourceDL(yt_dlp.YoutubeDL):
    """Bound empty continuation pages and network retries as well as entries."""

    def __init__(self, options: dict[str, object]) -> None:
        super().__init__(options)
        self._source_deadline = time.monotonic() + 90
        self._source_requests = 0

    def urlopen(self, req: object) -> object:
        if self._source_requests >= 12 or time.monotonic() >= self._source_deadline:
            raise SourceError("SOURCE_RESOLVE_FAILED")
        self._source_requests += 1
        return super().urlopen(req)


class SourceYtDlp:
    def list_channel(self, url: str) -> dict[str, object]:
        platform, canonical = source_url(url)
        if platform is not Platform.YOUTUBE:
            raise SourceError("SOURCE_LIST_UNSUPPORTED")
        options = _options() | {
            "allowed_extractors": ["^youtube:tab$"],
            "noplaylist": False,
            "playlistend": MAX_CANDIDATES,
            "extract_flat": True,
            "lazy_playlist": True,
            "skip_download": True,
        }
        try:
            with _SourceDL(options) as extractor:
                raw = extractor.extract_info(canonical, download=False, process=False)
                if not isinstance(raw, Mapping) or raw.get("_type") != "playlist":
                    raise SourceError("SOURCE_RESOLVE_FAILED")
                if raw.get("extractor_key") != "YoutubeTab":
                    raise SourceError("SOURCE_RESOLVE_FAILED")
                entries = list(islice(iter(raw.get("entries", ())), MAX_CANDIDATES))
                # Keep only fields consumed by normalization, never streams/formats/headers.
                fields = {
                    "id",
                    "url",
                    "webpage_url",
                    "ie_key",
                    "extractor_key",
                    "_type",
                    "title",
                    "channel",
                    "channel_id",
                    "uploader",
                    "duration",
                    "upload_date",
                    "view_count",
                    "thumbnail",
                    "thumbnails",
                    "availability",
                    "live_status",
                    "is_live",
                    "has_drm",
                }
                return {
                    key: raw.get(key)
                    for key in ("id", "channel_id", "channel", "title", "webpage_url")
                } | {
                    "entries": [
                        {key: item[key] for key in fields if key in item}
                        if isinstance(item, Mapping)
                        else None
                        for item in entries
                    ]
                }
        except SourceError:
            raise
        except Exception:
            raise SourceError("SOURCE_RESOLVE_FAILED") from None
