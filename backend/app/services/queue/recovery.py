import logging
from datetime import timedelta

from app.models.enums import JobStatus as S
from app.repositories.jobs import JobRepository
from app.services.queue.models import JobView
from app.services.queue.service import QueueService

logger = logging.getLogger(__name__)
STALE_SECONDS = 60


def recover_stale_jobs(
    queue: QueueService,
    *,
    stale_seconds: float = STALE_SECONDS,
    exclude_ids: frozenset[str] = frozenset(),
) -> int:
    now = queue.clock()
    before = now - timedelta(seconds=stale_seconds)
    with queue.sessions() as session:
        stale = [
            JobView.from_job(job)
            for job in JobRepository(session).stale_jobs(before, exclude_ids=exclude_ids)
        ]
    recovered = 0
    for view in stale:
        cancelled = view.cancel_requested_at is not None
        exhausted = view.attempt_count >= view.max_attempts
        status = S.CANCELLED if cancelled else S.FAILED if exhausted else S.QUEUED
        values: dict[str, object] = {
            "status": status,
            "current_step": status.value,
            "progress_percent": 0,
            "heartbeat_at": None,
            "started_at": None,
            "completed_at": now if status != S.QUEUED else None,
            "cancelled_at": now if cancelled else None,
            "error_code": "WORKER_LOST" if exhausted and not cancelled else None,
            "error_message": "Worker stopped before completing the job"
            if exhausted and not cancelled
            else None,
        }
        if queue._write(view, values, stale_before=before, operation="recover"):
            recovered += 1
            logger.info("Job recovered (%s -> %s)", view.id, status.value)
    return recovered
