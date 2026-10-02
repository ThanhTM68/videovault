import math
import re
from collections.abc import Mapping
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import JsonValue

from app.models.enums import Platform
from app.services.downloader.errors import (
    AuthenticationRequiredError,
    DownloadUnavailableError,
    InvalidVideoUrlError,
    MetadataResolveError,
)
from app.services.downloader.models import NormalizedVideo, VideoFormat
from app.services.downloader.platform import detect_platform, validate_video_url


def number(value: object, *, positive: bool = False) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        result = float(value)
        return (
            result if math.isfinite(result) and (result > 0 if positive else result >= 0) else None
        )
    except (ValueError, OverflowError):
        return None


def integer(value: object, *, positive: bool = False) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value if (value > 0 if positive else value >= 0) else None
    result = number(value, positive=positive)
    return int(result) if result is not None and result.is_integer() else None


def text(value: object, limit: int = 4096) -> str | None:
    return value[:limit] if isinstance(value, str) and value else None


def safe_metadata_url(value: object, *, identity: bool = False) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(validate_video_url(value))
    except InvalidVideoUrlError:
        return None
    query = (
        urlencode(
            [
                (key, val)
                for key, val in parse_qsl(parsed.query)
                if key in {"v", "video_id", "story_fbid", "id"}
            ]
        )
        if identity
        else ""
    )
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))


def check_single_video(info: Mapping[str, object]) -> None:
    if text(info.get("availability")) in {
        "private",
        "premium_only",
        "subscriber_only",
        "needs_auth",
    }:
        raise AuthenticationRequiredError()
    if info.get("_type", "video") != "video" or "entries" in info or info.get("is_live"):
        raise DownloadUnavailableError()
    if info.get("has_drm"):
        raise DownloadUnavailableError()


def normalize_formats(raw: object) -> tuple[VideoFormat, ...]:
    if not isinstance(raw, (list, tuple)):
        return ()
    formats = []
    seen: set[str] = set()
    for item in raw[:1000]:
        if not isinstance(item, Mapping):
            continue
        identity = item.get("format_id")
        if not isinstance(identity, str) or not identity or len(identity) > 512:
            continue
        if identity in seen:
            raise MetadataResolveError()
        seen.add(identity)
        formats.append(
            VideoFormat(
                format_id=identity,
                extension=text(item.get("ext"), 32),
                width=integer(item.get("width"), positive=True),
                height=integer(item.get("height"), positive=True),
                fps=number(item.get("fps"), positive=True),
                video_codec=text(item.get("vcodec"), 128),
                audio_codec=text(item.get("acodec"), 128),
                bitrate=number(item.get("tbr")),
                audio_bitrate=number(item.get("abr")),
                has_drm=bool(item.get("has_drm")),
            )
        )
    return tuple(formats)


def normalize_metadata(info: Mapping[str, object], platform: Platform, url: str) -> NormalizedVideo:
    check_single_video(info)
    identity = info.get("id")
    if not isinstance(identity, str) or not identity or len(identity) > 512:
        raise MetadataResolveError()
    canonical = safe_metadata_url(info.get("webpage_url"), identity=True)
    if canonical is None or detect_platform(canonical) != platform:
        canonical = safe_metadata_url(url, identity=True)
    if canonical is None:
        raise MetadataResolveError()
    uploaded = None
    date_string = info.get("upload_date")
    if isinstance(date_string, str) and re.fullmatch(r"\d{8}", date_string):
        try:
            uploaded = datetime.strptime(date_string, "%Y%m%d").date()
        except ValueError:
            pass
    # Deliberately exclude nested objects, descriptions, URLs, headers, cookies and
    # downloader options. This diagnostic subset is bounded independently of input.
    raw: dict[str, JsonValue] = {}
    for key in ("id", "title", "uploader", "uploader_id", "extractor", "ext"):
        value = text(info.get(key), 256)
        if value is not None:
            raw[key] = value
    for key in ("duration", "width", "height", "fps", "view_count", "like_count", "comment_count"):
        value = number(info.get(key))
        if value is not None:
            raw[key] = value
    return NormalizedVideo(
        platform=platform,
        platform_video_id=identity,
        canonical_url=canonical,
        title=text(info.get("title")),
        description=text(info.get("description"), 16384),
        creator=text(info.get("uploader") or info.get("channel")),
        creator_id=text(info.get("uploader_id") or info.get("channel_id")),
        creator_url=safe_metadata_url(info.get("uploader_url") or info.get("channel_url")),
        duration_seconds=number(info.get("duration")),
        upload_date=uploaded,
        view_count=integer(info.get("view_count")),
        like_count=integer(info.get("like_count")),
        comment_count=integer(info.get("comment_count")),
        width=integer(info.get("width"), positive=True),
        height=integer(info.get("height"), positive=True),
        fps=number(info.get("fps"), positive=True),
        thumbnail_url=safe_metadata_url(info.get("thumbnail")),
        formats=normalize_formats(info.get("formats")),
        raw_metadata=raw,
    )
