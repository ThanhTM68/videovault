import re
from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime
from typing import Protocol
from urllib.parse import urlsplit

from app.models.enums import Platform
from app.schemas.sources import BatchCandidate, SourceCapabilities, SourceSummary
from app.services.downloader.adapters.youtube import YoutubeAdapter
from app.services.downloader.base import AdapterCapabilities
from app.services.downloader.metadata import integer, number, safe_metadata_url, text
from app.services.downloader.source_ytdlp import SourceYtDlp
from app.services.sources.errors import SourceError
from app.services.sources.urls import CHANNEL_ID, source_url


class SourceAdapter(Protocol):
    capabilities: AdapterCapabilities

    def can_handle_source(self, url: str) -> bool: ...
    def resolve_source(self, url: str) -> tuple[SourceSummary, list[BatchCandidate | None]]: ...


class YouTubeSourceAdapter:
    capabilities = AdapterCapabilities(list_profile_or_channel=True, filter_duration=True)

    def __init__(self, core: SourceYtDlp | None = None) -> None:
        self.core = core or SourceYtDlp()
        self.video_adapter = YoutubeAdapter()

    def can_handle_source(self, url: str) -> bool:
        return source_url(url)[0] == Platform.YOUTUBE

    def resolve_source(self, url: str) -> tuple[SourceSummary, list[BatchCandidate | None]]:
        platform, canonical = source_url(url)
        if platform != Platform.YOUTUBE:
            raise SourceError("SOURCE_LIST_UNSUPPORTED")
        raw = self.core.list_channel(canonical)
        identity = raw.get("channel_id") or raw.get("id")
        identity = (
            identity if isinstance(identity, str) and re.fullmatch(CHANNEL_ID, identity) else None
        )
        requested = urlsplit(canonical).path.split("/")
        if requested[1] == "channel" and identity != requested[2]:
            raise SourceError("SOURCE_RESOLVE_FAILED")
        if raw.get("webpage_url"):
            try:
                resolved_platform, resolved_url = source_url(raw["webpage_url"])
                if resolved_platform != platform:
                    raise SourceError("SOURCE_RESOLVE_FAILED")
                resolved_path = urlsplit(resolved_url).path.split("/")
                if resolved_path[1] == "channel" and resolved_path[2] != identity:
                    raise SourceError("SOURCE_RESOLVE_FAILED")
                if (
                    resolved_path[1].startswith("@")
                    and requested[1].startswith("@")
                    and resolved_path[1].lower() != requested[1].lower()
                ):
                    raise SourceError("SOURCE_RESOLVE_FAILED")
            except (SourceError, TypeError):
                raise SourceError("SOURCE_RESOLVE_FAILED") from None
        summary = SourceSummary(
            platform=platform,
            source_id=identity,
            canonical_url=canonical,
            display_name=text(raw.get("channel") or raw.get("title"), 256),
            capabilities=SourceCapabilities(
                **{
                    key: value
                    for key, value in asdict(self.capabilities).items()
                    if key in SourceCapabilities.model_fields
                }
            ),
        )
        return summary, [self._candidate(item, identity) for item in raw["entries"][:100]]

    def _candidate(self, raw: object, source_id: str | None) -> BatchCandidate | None:
        if not isinstance(raw, Mapping):
            return None
        try:
            identity = raw.get("id")
            if not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", identity):
                return None
            if raw.get("ie_key", raw.get("extractor_key")) != "Youtube":
                return None
            if raw.get("_type") not in {None, "url", "video"}:
                return None
            if (
                raw.get("is_live")
                or raw.get("has_drm")
                or raw.get("live_status") in {"is_live", "is_upcoming", "post_live"}
            ):
                return None
            if raw.get("availability") in {
                "private",
                "premium_only",
                "subscriber_only",
                "needs_auth",
            }:
                return None
            if source_id and raw.get("channel_id") and raw["channel_id"] != source_id:
                return None
            for field in ("url", "webpage_url"):
                value = raw.get(field)
                if value is not None and (
                    not isinstance(value, str) or self.video_adapter._reference(value) != identity
                ):
                    return None
            canonical = f"https://www.youtube.com/watch?v={identity}"
            uploaded = None
            date_text = raw.get("upload_date")
            if isinstance(date_text, str) and re.fullmatch(r"\d{8}", date_text):
                try:
                    uploaded = datetime.strptime(date_text, "%Y%m%d").date()
                except ValueError:
                    pass
            thumbnail = safe_metadata_url(raw.get("thumbnail"))
            if thumbnail is None and isinstance(raw.get("thumbnails"), list):
                thumbnail = next(
                    (
                        url
                        for item in raw["thumbnails"][:10]
                        if isinstance(item, Mapping) and (url := safe_metadata_url(item.get("url")))
                    ),
                    None,
                )
            return BatchCandidate(
                platform=Platform.YOUTUBE,
                platform_video_id=identity,
                canonical_url=canonical,
                title=text(raw.get("title"), 512),
                creator=text(raw.get("channel") or raw.get("uploader"), 256),
                thumbnail_url=thumbnail[:1024] if thumbnail else None,
                duration_seconds=number(raw.get("duration")),
                upload_date=uploaded,
                view_count=integer(raw.get("view_count")),
            )
        except Exception:
            return None


class SourceAdapterRegistry:
    def __init__(self, adapters: tuple[SourceAdapter, ...] | None = None) -> None:
        self.adapters = adapters if adapters is not None else (YouTubeSourceAdapter(),)

    def select(self, url: str) -> tuple[SourceAdapter, str]:
        platform, canonical = source_url(url)
        if platform != Platform.YOUTUBE:
            raise SourceError("SOURCE_LIST_UNSUPPORTED")
        matches = [adapter for adapter in self.adapters if adapter.can_handle_source(canonical)]
        if len(matches) != 1:
            raise SourceError("SOURCE_UNSUPPORTED")
        return matches[0], canonical
