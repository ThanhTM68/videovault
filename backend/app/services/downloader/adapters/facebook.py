import re
from collections.abc import Mapping
from urllib.parse import parse_qs

from app.models.enums import Platform
from app.services.downloader.adapters.common import PlatformAdapter
from app.services.downloader.errors import MetadataResolveError


class FacebookAdapter(PlatformAdapter):
    platform = Platform.FACEBOOK
    hosts = frozenset({"facebook.com", "www.facebook.com", "m.facebook.com", "web.facebook.com"})
    extractor_names = ("facebook", "facebook:reel")
    extractor_keys = ("Facebook", "FacebookReel", "facebook:reel")

    def _reference(self, url: str) -> str | None:
        parsed = self._parse(url)
        if parsed is None:
            return None
        if parsed.path.rstrip("/") in {"/watch", "/video.php", "/video/video.php"}:
            values = parse_qs(parsed.query).get("v", [])
            return values[0] if len(values) == 1 and re.fullmatch(r"[0-9]+", values[0]) else None
        match = re.fullmatch(
            r"/(?:reel|[A-Za-z0-9_.-]+/videos(?:/[A-Za-z0-9_-]+)?)/([0-9]+)/?", parsed.path
        )
        return match[1] if match else None

    def can_handle(self, url: str) -> bool:
        return self._reference(url) is not None

    def extraction_url(self, url: str) -> str:
        super().extraction_url(url)
        return "https://www.facebook.com/watch/?v=" + self._reference(url)

    def canonical_url(self, info: Mapping[str, object], url: str, identity: str) -> str:
        if self._reference(url) != identity or (
            info.get("webpage_url") and self._reference(info["webpage_url"]) != identity
        ):
            raise MetadataResolveError()
        return f"https://www.facebook.com/watch/?v={identity}"
