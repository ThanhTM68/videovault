import re
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from app.models.enums import Platform
from app.services.downloader.errors import InvalidVideoUrlError

DetectedPlatform = Platform | Literal["unknown"]
_HOSTS = {
    "youtube.com": Platform.YOUTUBE,
    "youtu.be": Platform.YOUTUBE,
    "tiktok.com": Platform.TIKTOK,
    "douyin.com": Platform.DOUYIN,
    "instagram.com": Platform.INSTAGRAM,
    "facebook.com": Platform.FACEBOOK,
    "fb.watch": Platform.FACEBOOK,
}


def validate_video_url(url: str) -> str:
    """Validate syntax without network access. Never accept credentials or local paths."""
    if not isinstance(url, str) or len(url) > 8192 or re.search(r"[\s\x00-\x1f\x7f\\]", url):
        raise InvalidVideoUrlError()
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.netloc.endswith(":")
            or parsed.port not in {None, 80, 443}
        ):
            raise ValueError
        host = host.encode("idna").decode("ascii").lower()
        if len(host) > 253 or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in host.split(".")
        ):
            raise ValueError
    except (ValueError, UnicodeError):
        raise InvalidVideoUrlError() from None
    # Preserve video-identifying query parameters, discard fragment.
    port = f":{parsed.port}" if parsed.port is not None else ""
    return urlunsplit((parsed.scheme.lower(), host + port, parsed.path, parsed.query, ""))


def detect_platform(url: str) -> DetectedPlatform:
    host = urlsplit(validate_video_url(url)).hostname
    assert host is not None
    for domain, platform in _HOSTS.items():
        if host == domain or host.endswith("." + domain):
            return platform
    return "unknown"
