import re
from urllib.parse import urlsplit

from app.models.enums import Platform
from app.services.downloader.errors import InvalidVideoUrlError
from app.services.downloader.platform import validate_video_url
from app.services.sources.errors import SourceError

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
CHANNEL_ID = r"UC[A-Za-z0-9_-]{22}"
HANDLE = r"@[A-Za-z0-9_.-]{3,30}"


def source_url(value: str) -> tuple[Platform, str]:
    try:
        if len(value) > 2048:
            raise InvalidVideoUrlError()
        parsed = urlsplit(validate_video_url(value))
    except (InvalidVideoUrlError, ValueError):
        raise SourceError("SOURCE_URL_INVALID") from None
    if parsed.hostname in YOUTUBE_HOSTS:
        match = re.fullmatch(rf"/({HANDLE}|channel/{CHANNEL_ID})(?:/videos)?/?", parsed.path)
        if match:
            return Platform.YOUTUBE, f"https://www.youtube.com/{match[1]}/videos"
    other = {
        "www.tiktok.com": (Platform.TIKTOK, r"/@[A-Za-z0-9_.]{1,64}/?"),
        "tiktok.com": (Platform.TIKTOK, r"/@[A-Za-z0-9_.]{1,64}/?"),
        "www.douyin.com": (Platform.DOUYIN, r"/user/[A-Za-z0-9_-]{1,128}/?"),
        "www.instagram.com": (Platform.INSTAGRAM, r"/[A-Za-z0-9_.]{1,64}/?"),
        "instagram.com": (Platform.INSTAGRAM, r"/[A-Za-z0-9_.]{1,64}/?"),
        "www.facebook.com": (Platform.FACEBOOK, r"/[A-Za-z0-9_.]{1,128}/?"),
        "facebook.com": (Platform.FACEBOOK, r"/[A-Za-z0-9_.]{1,128}/?"),
    }
    policy = other.get(parsed.hostname)
    if policy and re.fullmatch(policy[1], parsed.path):
        return policy[0], f"https://{parsed.hostname}{parsed.path.rstrip('/')}"
    raise SourceError("SOURCE_UNSUPPORTED")
