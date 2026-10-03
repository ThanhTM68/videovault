from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import get_settings
from app.core.config import Settings
from app.models.enums import JobStatus
from app.schemas.queue import DownloadSubmission, QueueState, SubmissionResult, SubmittedJob
from app.services.queue.models import JobPage, JobView
from app.workers.manager import WorkerManager

router = APIRouter()


def get_manager(request: Request) -> WorkerManager:
    return request.app.state.worker_manager


Manager = Annotated[WorkerManager, Depends(get_manager)]


@router.get("/queue", response_model=QueueState)
def queue_state(manager: Manager) -> QueueState:
    return QueueState(paused=manager.paused)


@router.post("/downloads", response_model=SubmissionResult, status_code=202)
def submit_downloads(
    body: DownloadSubmission, manager: Manager, settings: Annotated[Settings, Depends(get_settings)]
) -> SubmissionResult:
    # The queue validates all payloads before committing any row.
    jobs = manager.queue.submit(
        body.payloads(settings.download_max_height, settings.storage_provider)
    )
    manager.notify()
    return SubmissionResult(jobs=[SubmittedJob(id=job.id) for job in jobs])


@router.get("/jobs", response_model=JobPage)
def list_jobs(
    manager: Manager,
    status: JobStatus | None = None,
    job_type: Annotated[str | None, Query(alias="type", max_length=50)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> JobPage:
    return manager.queue.list(status=status, job_type=job_type, page=page, page_size=page_size)


@router.get("/jobs/{job_id}", response_model=JobView)
def get_job(job_id: str, manager: Manager) -> JobView:
    return manager.queue.get(job_id)


@router.post("/jobs/{job_id}/cancel", response_model=JobView)
def cancel_job(job_id: str, manager: Manager) -> JobView:
    return manager.cancel(job_id)


@router.post("/jobs/{job_id}/retry", response_model=JobView)
def retry_job(job_id: str, manager: Manager) -> JobView:
    job = manager.queue.retry(job_id)
    manager.notify()
    return job


@router.post("/queue/pause")
def pause_queue(manager: Manager) -> dict[str, bool]:
    return manager.pause()


@router.post("/queue/resume")
def resume_queue(manager: Manager) -> dict[str, bool]:
    return manager.resume()
