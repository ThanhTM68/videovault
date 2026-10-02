import re
from collections.abc import Mapping
from urllib.parse import parse_qs

from app.models.enums import Platform
from app.services.downloader.adapters.common import PlatformAdapter, string_id
from app.services.downloader.errors import MetadataResolveError
from app.services.downloader.metadata import text


class YoutubeAdapter(PlatformAdapter):
    platform = Platform.YOUTUBE
    hosts = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"})
    extractor_names = ("youtube",)
    extractor_keys = ("Youtube",)

    def _reference(self, url: str) -> str | None:
        parsed = self._parse(url)
        if parsed is None:
            return None
        if parsed.hostname == "youtu.be":
            value = parsed.path.strip("/")
        elif parsed.path.rstrip("/") == "/watch":
            values = parse_qs(parsed.query).get("v", [])
            value = values[0] if len(values) == 1 else ""
        else:
            match = re.fullmatch(r"/shorts/([A-Za-z0-9_-]+)/?", parsed.path)
            value = match[1] if match else ""
        return value if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) else None

    def can_handle(self, url: str) -> bool:
        return self._reference(url) is not None

    def extraction_url(self, url: str) -> str:
        super().extraction_url(url)
        return "https://www.youtube.com/watch?v=" + self._reference(url)

    def canonical_url(self, info: Mapping[str, object], url: str, identity: str) -> str:
        if self._reference(url) != identity or (
            info.get("webpage_url") and self._reference(info["webpage_url"]) != identity
        ):
            raise MetadataResolveError()
        return f"https://www.youtube.com/watch?v={identity}"

    def creator_fields(
        self, info: Mapping[str, object]
    ) -> tuple[str | None, str | None, str | None]:
        return (
            text(info.get("channel") or info.get("uploader")),
            string_id(info.get("channel_id")),
            text(info.get("channel_url") or info.get("uploader_url")),
        )
