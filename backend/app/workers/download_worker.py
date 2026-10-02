import logging
import time
import traceback
from collections.abc import Callable
from threading import Event

from pydantic import ValidationError

from app.core.errors import AppError
from app.models.enums import JobStatus as S
from app.services.downloader.cancellation import DownloadCancelledError
from app.services.downloader.models import ProgressEvent
from app.services.downloader.models import ProgressPhase as P
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
    keep = False
    try:
        payload = DownloadPayload.model_validate(claim.payload)
        request = queue.downloader.prepare_request(**payload.model_dump())
        result = queue.downloader.download(
            request, ProgressBridge(queue, claim), cancellation=cancellation
        )
        if not cancellation.is_set():
            keep = queue.finish(claim)
    except DownloadCancelledError:
        queue.finish(claim, cancelled=True)
    except ValidationError:
        queue.finish(
            claim,
            error_code="INVALID_JOB_PAYLOAD",
            error_message="Persisted job payload is invalid",
        )
    except AppError as exc:
        queue.finish(
            claim, error_code=exc.code, error_message=exc.message, cancelled=cancellation.is_set()
        )
    except Exception as exc:
        log_failure(exc)
        queue.finish(
            claim,
            error_code="INTERNAL_SERVER_ERROR",
            error_message="An unexpected worker error occurred",
            cancelled=cancellation.is_set(),
        )
    finally:
        if result is not None and not keep:
            try:
                queue.downloader.discard_result(result)
            except Exception as exc:
                log_failure(exc)
            queue.finish(claim, cancelled=True)
