import logging

from app.services.downloader.base import ProgressCallback
from app.services.downloader.cancellation import DownloadCancelledError, check_cancelled
from app.services.downloader.models import ProgressEvent

logger = logging.getLogger(__name__)


class ProgressReporter:
    """A failing observer is disabled for this operation, leaving execution intact."""

    def __init__(self, callback: ProgressCallback | None = None) -> None:
        self._callback = callback

    def __call__(self, event: ProgressEvent) -> None:
        check_cancelled()
        if self._callback is not None:
            try:
                self._callback(event)
            except DownloadCancelledError:
                raise
            except Exception as exc:
                logger.warning("Progress observer disabled (%s)", type(exc).__name__)
                self._callback = None
