import logging
from collections.abc import Mapping

from app.models.enums import Platform
from app.services.downloader.adapters.common import PlatformAdapter
from app.services.downloader.adapters.douyin import DouyinAdapter
from app.services.downloader.adapters.facebook import FacebookAdapter
from app.services.downloader.adapters.instagram import InstagramAdapter
from app.services.downloader.adapters.tiktok import TikTokAdapter
from app.services.downloader.adapters.youtube import YoutubeAdapter
from app.services.downloader.base import AdapterCapabilities, DownloaderAdapter
from app.services.downloader.errors import UnsupportedPlatformError
from app.services.downloader.platform import detect_platform

logger = logging.getLogger(__name__)


class AdapterRegistry:
    def __init__(self, adapters: Mapping[Platform, DownloaderAdapter] | None = None) -> None:
        self._adapters: dict[Platform, DownloaderAdapter] = (
            dict(adapters)
            if adapters is not None
            else {
                Platform.YOUTUBE: YoutubeAdapter(),
                Platform.TIKTOK: TikTokAdapter(),
                Platform.DOUYIN: DouyinAdapter(),
                Platform.INSTAGRAM: InstagramAdapter(),
                Platform.FACEBOOK: FacebookAdapter(),
            }
        )

    def select(self, url: str) -> DownloaderAdapter:
        platform = detect_platform(url)
        if not isinstance(platform, Platform) or platform not in self._adapters:
            raise UnsupportedPlatformError()
        adapter = self._adapters[platform]
        if isinstance(adapter, PlatformAdapter) and not adapter.can_handle(url):
            raise UnsupportedPlatformError()
        logger.info("Platform adapter selected (%s)", platform.value)
        return adapter

    def capabilities(self) -> dict[Platform, AdapterCapabilities]:
        return {platform: adapter.capabilities for platform, adapter in self._adapters.items()}
