from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.services.downloader.models import (
    DownloadRequest,
    NormalizedVideo,
    ProgressEvent,
    VideoFormat,
)

ProgressCallback = Callable[[ProgressEvent], None]


@dataclass(frozen=True)
class AdapterCapabilities:
    resolve_single: bool = True
    download_single: bool = True
    list_profile_or_channel: bool = False
    sort_newest: bool = False
    sort_oldest: bool = False
    sort_views: bool = False
    filter_views: bool = False
    filter_date: bool = False
    filter_duration: bool = False


class DownloaderAdapter(Protocol):
    capabilities: AdapterCapabilities

    def resolve(self, url: str) -> NormalizedVideo: ...

    def get_formats(self, video: NormalizedVideo) -> tuple[VideoFormat, ...]: ...

    def download(
        self,
        video: NormalizedVideo,
        request: DownloadRequest,
        output_stem: Path,
        progress: ProgressCallback,
    ) -> Path:
        """Return one complete candidate inside output_stem.parent; service probes it."""
        ...
