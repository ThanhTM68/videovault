import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ConflictError, NotFoundError
from app.models import Job
from app.models.enums import JobStatus as S
from app.repositories.jobs import JobRepository
from app.services.downloader.service import DownloaderService
from app.services.library.service import LibraryService
from app.services.queue.models import Claim, DownloadPayload, JobPage, JobView
from app.services.queue.state_machine import ACTIVE, validate_transition
from app.services.storage.service import StorageService

logger = logging.getLogger(__name__)


class QueueService:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        downloader: DownloaderService,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        storage: StorageService | None = None,
    ) -> None:
        self.sessions = sessions
        self.downloader = downloader
        self.clock = clock
        self.storage = storage or StorageService(downloader.settings, sessions)
        self.library = LibraryService(sessions, self.storage)

    def skip_duplicate(self, claim: Claim) -> bool:
        view = self.get(claim.id)
        if view.attempt_count != claim.attempt or view.status != S.RESOLVING:
            return False
        changed = self._write(
            view,
            {
                "status": S.SKIPPED_DUPLICATE,
                "current_step": "skipped_duplicate",
                "completed_at": self.clock(),
            },
            require_uncancelled=True,
        )
        if changed:
            logger.info("Duplicate skipped (%s)", claim.id)
        return changed is not None

    def submit(self, payloads: Sequence[DownloadPayload]) -> list[JobView]:
        if not 1 <= len(payloads) <= 100:
            raise ConflictError("Submit between 1 and 100 URLs")
        # Local configuration validation only; no resolution or remote storage I/O.
        for payload in payloads:
            self.downloader.prepare_request(
                **payload.model_dump(exclude={"force", "storage_target"})
            )
            self.storage.check_available(payload.storage_target)
        with self.sessions.begin() as session:
            repository = JobRepository(session)
            rows = [
                repository.add(Job(type="download", payload_json=p.model_dump(mode="json")))
                for p in payloads
            ]
            views = [JobView.from_job(row) for row in rows]
        logger.info("Jobs created (%s)", len(views))
        return views

    def get(self, job_id: str) -> JobView:
        with self.sessions() as session:
            job = JobRepository(session).get_by_id(job_id)
            if job is None:
                raise NotFoundError("Job was not found")
            return JobView.from_job(job)

    def list(
        self,
        *,
        status: S | None = None,
        job_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> JobPage:
        with self.sessions() as session:
            jobs, total = JobRepository(session).list_page(
                status=status, job_type=job_type, page=page, page_size=page_size
            )
            return JobPage(
                items=[JobView.from_job(job) for job in jobs],
                total=total,
                page=page,
                page_size=page_size,
            )

    def claim(self) -> Claim | None:
        validate_transition(S.QUEUED, S.RESOLVING)
        with self.sessions.begin() as session:
            job = JobRepository(session).claim(self.clock())
            claim = Claim(job.id, job.attempt_count, dict(job.payload_json)) if job else None
        if claim:
            logger.info("Job claimed (%s attempt %s)", claim.id, claim.attempt)
        return claim

    def _write(
        self,
        view: JobView,
        values: dict[str, object],
        *,
        require_uncancelled: bool = False,
        stale_before: datetime | None = None,
        operation: str = "execute",
        on_completed: Callable[[Session], None] | None = None,
    ) -> JobView | None:
        target = values.get("status", view.status)
        if target != view.status:
            validate_transition(view.status, target, operation=operation)
        with self.sessions.begin() as session:
            job = JobRepository(session).compare_and_set(
                view.id,
                view.attempt_count,
                view.status,
                values,
                require_uncancelled=require_uncancelled,
                stale_before=stale_before,
                check_cancel_request=operation == "recover",
                cancel_request=view.cancel_requested_at,
            )
            if job and on_completed:
                on_completed(session)
            if job and (job.status in {S.FAILED, S.CANCELLED} or operation == "recover"):
                from app.repositories.library import LibraryRepository

                LibraryRepository(session).close_attempts(
                    view.id,
                    view.attempt_count,
                    cancelled=job.status == S.CANCELLED,
                    code=job.error_code or "WORKER_LOST",
                    message=job.error_message or "Worker stopped before completing the job",
                    now=self.clock(),
                )
            return JobView.from_job(job) if job else None

    def cancel(self, job_id: str) -> JobView:
        # Read and write use separate short transactions; CAS handles a concurrent claim.
        for _ in range(4):
            view = self.get(job_id)
            if view.status not in ACTIVE | {S.QUEUED}:
                raise ConflictError("Only queued or running jobs can be cancelled")
            if view.cancel_requested_at is not None:
                return view
            now = self.clock()
            values: dict[str, object] = {"cancel_requested_at": now}
            if view.status == S.QUEUED:
                values.update(
                    status=S.CANCELLED, current_step="cancelled", cancelled_at=now, completed_at=now
                )
            changed = self._write(view, values)
            if changed:
                logger.info("Job cancellation requested (%s)", job_id)
                return changed
        raise ConflictError("Job changed; try the operation again")

    def retry(self, job_id: str) -> JobView:
        view = self.get(job_id)
        validate_transition(view.status, S.QUEUED, operation="retry")
        if view.attempt_count >= view.max_attempts:
            raise ConflictError("Job has exhausted its allowed attempts")
        changed = self._write(
            view,
            {
                "status": S.QUEUED,
                "progress_percent": 0,
                "current_step": None,
                "started_at": None,
                "heartbeat_at": None,
                "completed_at": None,
                "cancelled_at": None,
                "cancel_requested_at": None,
                "error_code": None,
                "error_message": None,
            },
            operation="retry",
        )
        if changed is None:
            raise ConflictError("Job changed; try the operation again")
        logger.info("Job retried (%s)", job_id)
        return changed

    def heartbeat(self, claim: Claim) -> bool | None:
        """Return cancel request flag; None means this attempt no longer owns the row."""
        with self.sessions.begin() as session:
            job = JobRepository(session).heartbeat(claim.id, claim.attempt, self.clock())
            return job.cancel_requested_at is not None if job else None

    def progress(self, claim: Claim, status: S, step: str, percent: float | None) -> None:
        view = self.get(claim.id)
        if view.attempt_count != claim.attempt or view.status not in ACTIVE:
            return
        # Split-stream hooks can report processing before the second stream starts.
        rank = {S.RESOLVING: 0, S.DOWNLOADING: 1, S.PROCESSING: 2, S.UPLOADING: 3}
        if rank[status] < rank[view.status]:
            return
        self._write(
            view,
            {
                "status": status,
                "current_step": step,
                "progress_percent": min(percent, 99) if percent is not None else 0,
            },
        )

    def finish(
        self,
        claim: Claim,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        cancelled: bool = False,
        on_completed: Callable[[Session], None] | None = None,
    ) -> bool:
        for _ in range(4):
            view = self.get(claim.id)
            if view.attempt_count != claim.attempt or view.status not in ACTIVE:
                return False
            now = self.clock()
            if view.cancel_requested_at is not None and not cancelled and not error_code:
                # Caller must discard successful output before acknowledging cancellation.
                return False
            # Cancellation wins if it committed before successful finalization.
            cancel = cancelled or view.cancel_requested_at is not None
            status = S.CANCELLED if cancel else S.FAILED if error_code else S.COMPLETED
            values: dict[str, object] = {
                "status": status,
                "current_step": status.value,
                "completed_at": now,
                "heartbeat_at": now,
                "cancelled_at": now if cancel else None,
                "error_code": None if cancel else error_code,
                "error_message": None if cancel else error_message,
            }
            if status == S.COMPLETED:
                values["progress_percent"] = 100
            changed = self._write(
                view,
                values,
                require_uncancelled=not cancel,
                on_completed=on_completed if status == S.COMPLETED else None,
            )
            if changed:
                logger.info("Job %s (%s)", status.value, claim.id)
                return status == S.COMPLETED
        raise ConflictError("Job finalization raced with another operation")
