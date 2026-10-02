from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models import Job
from app.models.enums import JobStatus


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, job_id: str) -> Job | None:
        return self.session.get(Job, job_id)

    def add(self, job: Job) -> Job:
        self.session.add(job)
        self.session.flush()
        return job

    def update_state(self, job: Job, *, status: JobStatus, progress_percent: float) -> Job:
        job.status = status
        job.progress_percent = progress_percent
        self.session.flush()
        return job

    def delete(self, job: Job) -> None:
        self.session.delete(job)
        self.session.flush()

    def list_page(
        self, *, status: JobStatus | None, job_type: str | None, page: int, page_size: int
    ) -> tuple[list[Job], int]:
        filters = []
        if status is not None:
            filters.append(Job.status == status)
        if job_type is not None:
            filters.append(Job.type == job_type)
        total = self.session.scalar(select(func.count()).select_from(Job).where(*filters)) or 0
        rows = self.session.scalars(
            select(Job)
            .where(*filters)
            .order_by(Job.created_at, Job.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), total

    def claim(self, now: datetime) -> Job | None:
        eligible = (
            Job.type == "download",
            Job.status == JobStatus.QUEUED,
            Job.attempt_count < Job.max_attempts,
            Job.cancel_requested_at.is_(None),
        )
        candidate = select(Job.id).where(*eligible).order_by(Job.created_at, Job.id).limit(1)
        # No prior SELECT: SQLite serializes this write, including candidate selection.
        return self.session.scalars(
            update(Job)
            .where(Job.id == candidate.scalar_subquery(), *eligible)
            .values(
                status=JobStatus.RESOLVING,
                current_step="resolving",
                progress_percent=0,
                attempt_count=Job.attempt_count + 1,
                started_at=now,
                heartbeat_at=now,
                completed_at=None,
                cancelled_at=None,
                error_code=None,
                error_message=None,
            )
            .returning(Job)
            .execution_options(synchronize_session=False)
        ).one_or_none()

    def compare_and_set(
        self,
        job_id: str,
        attempt: int,
        status: JobStatus,
        values: dict[str, object],
        *,
        require_uncancelled: bool = False,
        stale_before: datetime | None = None,
        check_cancel_request: bool = False,
        cancel_request: datetime | None = None,
    ) -> Job | None:
        conditions = [Job.id == job_id, Job.attempt_count == attempt, Job.status == status]
        if require_uncancelled:
            conditions.append(Job.cancel_requested_at.is_(None))
        if stale_before is not None:
            conditions.append(self.stale_condition(stale_before))
        if check_cancel_request:
            conditions.append(Job.cancel_requested_at == cancel_request)
        return self.session.scalars(
            update(Job)
            .where(*conditions)
            .values(**values)
            .returning(Job)
            .execution_options(synchronize_session=False)
        ).one_or_none()

    def heartbeat(self, job_id: str, attempt: int, now: datetime) -> Job | None:
        return self.session.scalars(
            update(Job)
            .where(
                Job.id == job_id,
                Job.attempt_count == attempt,
                Job.status.in_(
                    [
                        JobStatus.RESOLVING,
                        JobStatus.DOWNLOADING,
                        JobStatus.PROCESSING,
                        JobStatus.UPLOADING,
                    ]
                ),
            )
            .values(heartbeat_at=now)
            .returning(Job)
            .execution_options(synchronize_session=False)
        ).one_or_none()

    @staticmethod
    def stale_condition(before: datetime) -> ColumnElement[bool]:
        return func.coalesce(Job.heartbeat_at, Job.started_at, Job.created_at) < before

    def stale_jobs(
        self, before: datetime, *, exclude_ids: frozenset[str] = frozenset()
    ) -> list[Job]:
        return list(
            self.session.scalars(
                select(Job).where(
                    Job.status.in_(
                        [
                            JobStatus.RESOLVING,
                            JobStatus.DOWNLOADING,
                            JobStatus.PROCESSING,
                            JobStatus.UPLOADING,
                        ]
                    ),
                    self.stale_condition(before),
                    Job.id.not_in(exclude_ids),
                )
            ).all()
        )
