import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from app.core.config import Settings
from app.core.errors import AppError, MediaValidationError
from app.models.enums import Platform
from app.services.downloader.adapters.registry import AdapterRegistry
from app.services.downloader.base import AdapterCapabilities, DownloaderAdapter, ProgressCallback
from app.services.downloader.cancellation import cancellation_scope, check_cancelled
from app.services.downloader.errors import DownloadFailedError, UnsupportedPlatformError
from app.services.downloader.models import (
    DownloadRequest,
    NormalizedVideo,
    ProgressEvent,
    ProgressPhase,
)
from app.services.downloader.paths import (
    confined_path,
    create_workspace,
    remove_workspace,
    video_filename,
)
from app.services.downloader.platform import detect_platform, validate_video_url
from app.services.downloader.progress import ProgressReporter
from app.services.downloader.selector import select_formats
from app.services.media.probe import ProbeResult, probe_video

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DownloadResult:
    video: NormalizedVideo
    path: Path
    probe: ProbeResult


class DownloaderService:
    def __init__(
        self, settings: Settings, adapters: Mapping[Platform, DownloaderAdapter] | None = None
    ) -> None:
        self._settings = settings
        self._registry = AdapterRegistry(adapters)

    def _adapter(self, url: str) -> DownloaderAdapter:
        return self._registry.select(url)

    def capabilities(self) -> dict[Platform, AdapterCapabilities]:
        return self._registry.capabilities()

    @property
    def settings(self) -> Settings:
        return self._settings

    def resolve(self, url: str) -> NormalizedVideo:
        url = validate_video_url(url)
        adapter = self._adapter(url)
        if not adapter.capabilities.resolve_single:
            raise UnsupportedPlatformError()
        video = adapter.resolve(url)
        if video.platform != detect_platform(url):
            raise UnsupportedPlatformError()
        return video

    def prepare_request(
        self,
        url: str,
        *,
        max_height: int | None = None,
        output_directory: Path | None = None,
        preferred_container: str = "mp4",
        audio_enabled: bool = True,
    ) -> DownloadRequest:
        request = DownloadRequest(
            url=validate_video_url(url),
            max_height=max_height if max_height is not None else self._settings.download_max_height,
            output_directory=confined_path(
                self._settings.temp_storage_root,
                output_directory or self._settings.temp_storage_root,
            ),
            preferred_container=preferred_container,
            audio_enabled=audio_enabled,
        )
        self._adapter(request.url)
        return request

    def download(
        self,
        request: DownloadRequest,
        progress: ProgressCallback | None = None,
        *,
        cancellation: Event | None = None,
    ) -> DownloadResult:
        with cancellation_scope(cancellation):
            return self._download(request, progress)

    def _download(
        self, request: DownloadRequest, progress: ProgressCallback | None
    ) -> DownloadResult:
        check_cancelled()
        root = self._settings.temp_storage_root
        confined_path(root, request.output_directory)
        adapter = self._adapter(request.url)
        if not adapter.capabilities.download_single:
            raise UnsupportedPlatformError()
        reporter = ProgressReporter(progress)
        workspace = None
        try:
            reporter(ProgressEvent(phase=ProgressPhase.RESOLVING))
            video = self.resolve(request.url)
            check_cancelled()
            # Also enforce the configured ceiling for externally constructed requests.
            effective_height = min(request.max_height, self._settings.download_max_height)
            select_formats(
                adapter.get_formats(video),
                effective_height,
                request.preferred_container,
                request.audio_enabled,
            )
            workspace = create_workspace(root, request.output_directory)
            execution_request = request.model_copy(
                update={"output_directory": workspace, "max_height": effective_height}
            )
            reporter(ProgressEvent(phase=ProgressPhase.DOWNLOADING))

            def adapter_progress(event: ProgressEvent) -> None:
                # Only the service can publish completion after probing the output.
                if event.phase != ProgressPhase.COMPLETED:
                    reporter(event)

            candidate = adapter.download(
                video, execution_request, workspace / video_filename(video), adapter_progress
            )
            check_cancelled()
            if candidate.is_symlink():
                raise MediaValidationError()
            path = confined_path(workspace, candidate)
            if path.suffix.lower() != "." + request.preferred_container or path.is_symlink():
                raise MediaValidationError()
            reporter(ProgressEvent(phase=ProgressPhase.VALIDATING))
            probe = probe_video(path)
            check_cancelled()
            if probe.height > effective_height or probe.has_audio != request.audio_enabled:
                raise MediaValidationError()
            logger.info("Temporary video validation succeeded (%s)", video.platform.value)
            reporter(ProgressEvent(phase=ProgressPhase.COMPLETED, percent=100))
            return DownloadResult(video, path, probe)
        except Exception as exc:
            logger.warning(
                "Download operation failed (%s)",
                exc.code if isinstance(exc, AppError) else type(exc).__name__,
            )
            if workspace is not None:
                try:
                    remove_workspace(root, workspace)
                except (OSError, AppError) as cleanup_error:
                    logger.warning("Temporary cleanup failed (%s)", type(cleanup_error).__name__)
            if isinstance(exc, OSError):
                raise DownloadFailedError() from None
            raise

    def discard_result(self, result: DownloadResult) -> None:
        """Remove only this invocation's validated temporary workspace."""
        remove_workspace(self._settings.temp_storage_root, result.path.parent)
