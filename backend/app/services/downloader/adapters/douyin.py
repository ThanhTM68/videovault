import re
from collections.abc import Mapping
from urllib.parse import urlsplit

from app.models.enums import Platform
from app.services.downloader.adapters.common import PlatformAdapter, string_id
from app.services.downloader.errors import MetadataResolveError
from app.services.downloader.metadata import text


class DouyinAdapter(PlatformAdapter):
    platform = Platform.DOUYIN
    hosts = frozenset({"douyin.com", "www.douyin.com"})
    extractor_names = ("douyin",)
    extractor_keys = ("Douyin",)

    def can_handle(self, url: str) -> bool:
        parsed = self._parse(url)
        return parsed is not None and bool(re.fullmatch(r"/video/[0-9]+/?", parsed.path))

    def extraction_url(self, url: str) -> str:
        url = super().extraction_url(url)
        return "https://www.douyin.com" + urlsplit(url).path.rstrip("/")

    def canonical_url(self, info: Mapping[str, object], url: str, identity: str) -> str:
        if not re.fullmatch(r"[0-9]+", identity):
            raise MetadataResolveError()
        for candidate in (url, info.get("webpage_url")):
            if (
                isinstance(candidate, str)
                and urlsplit(candidate).path.rstrip("/") != f"/video/{identity}"
            ):
                raise MetadataResolveError()
        return f"https://www.douyin.com/video/{identity}"

    def creator_fields(
        self, info: Mapping[str, object]
    ) -> tuple[str | None, str | None, str | None]:
        return (
            text(info.get("channel") or info.get("creator") or info.get("uploader")),
            string_id(info.get("uploader_id")),
            text(info.get("uploader_url") or info.get("channel_url")),
        )
