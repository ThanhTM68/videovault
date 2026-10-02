from sqlalchemy.orm import Session

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
