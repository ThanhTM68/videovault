import logging
import time
import traceback
from collections.abc import Callable
from threading import Event

from pydantic import ValidationError

from app.core.errors import AppError, ConflictError
from app.models.enums import JobStatus as S
from app.repositories.library import LibraryRepository
from app.services.downloader.cancellation import DownloadCancelledError
from app.services.downloader.models import ProgressEvent
from app.services.downloader.models import ProgressPhase as P
from app.services.library.locks import identity_lock
from app.services.queue.models import Claim, DownloadPayload
from app.services.queue.service import QueueService

logger = logging.getLogger(__name__)


def log_failure(exc: Exception) -> None:
    locations = " -> ".join(
        f"{f.filename}:{f.lineno} ({f.name})" for f in traceback.extract_tb(exc.__traceback__)
    )
    logger.error("Worker failure %s at %s", type(exc).__name__, locations)


class ProgressBridge:
    def __init__(
        self, queue: QueueService, claim: Claim, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.queue, self.claim, self.clock = queue, claim, clock
        self.last_phase: P | None = None
        self.last_percent: float | None = None
        self.last_time = float("-inf")

    def __call__(self, event: ProgressEvent) -> None:
        # Completion is committed only after download returns a validated result.
        if event.phase == P.COMPLETED:
            return
        rank = {P.RESOLVING: 0, P.DOWNLOADING: 1, P.PROCESSING: 2, P.VALIDATING: 3}
        if self.last_phase is not None and rank[event.phase] < rank[self.last_phase]:
            return
        now = self.clock()
        phase_changed = event.phase != self.last_phase
        elapsed = now - self.last_time
        delta = event.percent != self.last_percent and (
            event.percent is None
            or self.last_percent is None
            or abs(event.percent - self.last_percent) >= 1
        )
        if not (phase_changed or elapsed >= 5 or elapsed >= 1 and delta):
            return
        status = {
            P.RESOLVING: S.RESOLVING,
            P.DOWNLOADING: S.DOWNLOADING,
            P.PROCESSING: S.PROCESSING,
            P.VALIDATING: S.PROCESSING,
        }[event.phase]
        self.queue.progress(self.claim, status, event.phase.value, event.percent)
        self.last_phase, self.last_percent, self.last_time = event.phase, event.percent, now


def execute_download(queue: QueueService, claim: Claim, cancellation: Event) -> None:
    result = None
    finalized = None
    keep = False
    cancelled = False
    error_code = None
    error_message = None
    try:
        payload = DownloadPayload.model_validate(claim.payload)
        request = queue.downloader.prepare_request(**payload.model_dump(exclude={"force"}))
        if cancellation.is_set():
            raise DownloadCancelledError()
        metadata = queue.downloader.resolve(request.url)
        with identity_lock(metadata.platform.value, metadata.platform_video_id, cancellation):
            _, event_id = queue.library.begin_attempt(metadata, payload, claim)
            if event_id is None:
                if not queue.skip_duplicate(claim):
                    queue.finish(claim, cancelled=True)
                return
            result = queue.downloader.download(
                request, ProgressBridge(queue, claim), cancellation=cancellation
            )
            if (result.video.platform, result.video.platform_video_id) != (
                metadata.platform,
                metadata.platform_video_id,
            ):
                raise ConflictError("Source identity changed during download")
            if cancellation.is_set():
                raise DownloadCancelledError()
            finalized = queue.library.files.finalize(result, cancellation)
            if not cancellation.is_set():
                keep = queue.finish(
                    claim,
                    on_completed=lambda session: LibraryRepository(session).save_result(
                        event_id, result, finalized
                    ),
                )
    except DownloadCancelledError:
        cancelled = True
    except ValidationError:
        error_code = "INVALID_JOB_PAYLOAD"
        error_message = "Persisted job payload is invalid"
    except AppError as exc:
        error_code, error_message = exc.code, exc.message
    except Exception as exc:
        log_failure(exc)
        error_code = "INTERNAL_SERVER_ERROR"
        error_message = "An unexpected worker error occurred"
    finally:
        if finalized is not None and not keep:
            try:
                queue.library.files.delete(finalized.key)
            except Exception as exc:
                log_failure(exc)
        if result is not None:
            try:
                queue.downloader.discard_result(result)
            except Exception as exc:
                log_failure(exc)
        # Acknowledge failures/cancellation only after owned output cleanup finishes.
        if not keep and (result is not None or error_code or cancelled):
            queue.finish(
                claim,
                error_code=error_code,
                error_message=error_message,
                cancelled=cancelled or cancellation.is_set() or not error_code,
            )
