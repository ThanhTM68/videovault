import re
from collections.abc import Mapping
from urllib.parse import urlsplit

from app.models.enums import Platform
from app.services.downloader.adapters.common import PlatformAdapter
from app.services.downloader.errors import MetadataResolveError


class InstagramAdapter(PlatformAdapter):
    platform = Platform.INSTAGRAM
    hosts = frozenset({"instagram.com", "www.instagram.com"})
    extractor_names = ("instagram",)
    extractor_keys = ("Instagram",)

    def can_handle(self, url: str) -> bool:
        parsed = self._parse(url)
        return parsed is not None and bool(
            re.fullmatch(r"/(?:p|tv|reel|reels)/[A-Za-z0-9_-]+/?", parsed.path)
        )

    def extraction_url(self, url: str) -> str:
        url = super().extraction_url(url)
        path = urlsplit(url).path.replace("/reels/", "/reel/").rstrip("/")
        return "https://www.instagram.com" + path + "/"

    def canonical_url(self, info: Mapping[str, object], url: str, identity: str) -> str:
        requested = self.extraction_url(url)
        page = self.extraction_url(info.get("webpage_url") or url)
        if (
            urlsplit(requested).path.strip("/").split("/")[-1]
            != urlsplit(page).path.strip("/").split("/")[-1]
        ):
            raise MetadataResolveError()
        return page
