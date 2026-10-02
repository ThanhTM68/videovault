import re
from collections.abc import Mapping
from urllib.parse import urlsplit

from app.models.enums import Platform
from app.services.downloader.adapters.common import PlatformAdapter, string_id
from app.services.downloader.errors import MetadataResolveError
from app.services.downloader.metadata import text


class TikTokAdapter(PlatformAdapter):
    platform = Platform.TIKTOK
    hosts = frozenset(
        {"tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}
    )
    extractor_names = ("tiktok", "vm.tiktok")
    extractor_keys = ("TikTok",)
    block_challenges = True

    def can_handle(self, url: str) -> bool:
        parsed = self._parse(url)
        if parsed is None:
            return False
        if parsed.hostname in {"vm.tiktok.com", "vt.tiktok.com"}:
            return bool(re.fullmatch(r"/[A-Za-z0-9]+/?", parsed.path))
        return bool(
            re.fullmatch(
                r"/(?:@[A-Za-z0-9_.-]+/video/[0-9]+|share/video/[0-9]+|t/[A-Za-z0-9]+)/?",
                parsed.path,
            )
        )

    def extraction_url(self, url: str) -> str:
        url = super().extraction_url(url)
        parsed = urlsplit(url)
        host = (
            parsed.hostname
            if parsed.hostname in {"vm.tiktok.com", "vt.tiktok.com"}
            else "www.tiktok.com"
        )
        return f"https://{host}{parsed.path}"

    def canonical_url(self, info: Mapping[str, object], url: str, identity: str) -> str:
        if not re.fullmatch(r"[0-9]+", identity):
            raise MetadataResolveError()
        for candidate in (url, info.get("webpage_url")):
            if isinstance(candidate, str):
                match = re.fullmatch(
                    r"/(?:@[A-Za-z0-9_.-]+|share)/video/([0-9]+)/?", urlsplit(candidate).path
                )
                if match and match[1] != identity:
                    raise MetadataResolveError()
        page = info.get("webpage_url") or url
        parsed = urlsplit(page)
        if "/video/" in parsed.path:
            return "https://www.tiktok.com" + parsed.path.rstrip("/")
        username = text(info.get("uploader"), 128)
        if username and re.fullmatch(r"[A-Za-z0-9_.-]+", username):
            return f"https://www.tiktok.com/@{username}/video/{identity}"
        return f"https://www.tiktok.com/share/video/{identity}"

    def creator_fields(
        self, info: Mapping[str, object]
    ) -> tuple[str | None, str | None, str | None]:
        return (
            text(info.get("creator") or info.get("channel") or info.get("uploader")),
            string_id(info.get("uploader_id")),
            text(info.get("uploader_url") or info.get("channel_url")),
        )
