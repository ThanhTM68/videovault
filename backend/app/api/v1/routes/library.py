from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.models.enums import DownloadStatus, Platform
from app.schemas.library import HistoryPage, NamedItem, NameInput, VideoDetail, VideoPage
from app.schemas.queue import SubmissionResult, SubmittedJob
from app.services.library.service import LibraryService
from app.services.queue.models import DownloadPayload

router = APIRouter()


def library(request: Request) -> LibraryService:
    return request.app.state.worker_manager.queue.library


Library = Annotated[LibraryService, Depends(library)]
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.get("/videos", response_model=VideoPage)
def list_videos(
    service: Library,
    page: Page = 1,
    page_size: PageSize = 25,
    search: Annotated[str, Query(max_length=255)] = "",
    platform: Platform | None = None,
    has_file: bool | None = None,
    has_download_history: bool | None = None,
    tag_id: str | None = None,
    collection_id: str | None = None,
) -> VideoPage:
    return service.list(
        page=page,
        page_size=page_size,
        search=search,
        platform=platform,
        has_file=has_file,
        has_download_history=has_download_history,
        tag_id=tag_id,
        collection_id=collection_id,
    )


@router.get("/videos/{video_id}", response_model=VideoDetail)
def video_detail(video_id: str, service: Library) -> VideoDetail:
    return service.detail(video_id)


@router.post("/videos/{video_id}/refresh-files", response_model=VideoDetail)
def refresh_files(video_id: str, service: Library) -> VideoDetail:
    return service.detail(video_id, verify_remote=True)


@router.get("/history", response_model=HistoryPage)
def history(
    service: Library,
    page: Page = 1,
    page_size: PageSize = 25,
    status: DownloadStatus | None = None,
    platform: Platform | None = None,
) -> HistoryPage:
    return service.history(page=page, page_size=page_size, status=status, platform=platform)


@router.delete("/videos/{video_id}/file", response_model=VideoDetail)
def delete_file(video_id: str, service: Library) -> VideoDetail:
    return service.destroy(video_id, "file")


@router.delete("/videos/{video_id}/history", response_model=VideoDetail)
def remove_history(video_id: str, service: Library) -> VideoDetail:
    return service.destroy(video_id, "history")


@router.delete("/videos/{video_id}/all", response_model=VideoDetail)
def delete_everything(video_id: str, service: Library) -> VideoDetail:
    return service.destroy(video_id, "all")


@router.post("/videos/{video_id}/redownload", response_model=SubmissionResult, status_code=202)
def redownload(video_id: str, service: Library, request: Request) -> SubmissionResult:
    manager = request.app.state.worker_manager
    jobs = manager.queue.submit(
        [
            DownloadPayload(
                url=service.source(video_id),
                max_height=request.app.state.settings.download_max_height,
                force=True,
                storage_target=request.app.state.settings.storage_provider,
            )
        ]
    )
    manager.notify()
    return SubmissionResult(jobs=[SubmittedJob(id=job.id) for job in jobs])


@router.get("/collections", response_model=list[NamedItem])
def collections(service: Library) -> list[NamedItem]:
    return service.organization("collections")


@router.post("/collections", response_model=NamedItem, status_code=201)
def create_collection(body: NameInput, service: Library) -> NamedItem:
    return service.organization("collections", body.name)


@router.post("/collections/{item_id}/videos/{video_id}", response_model=VideoDetail)
def add_collection(item_id: str, video_id: str, service: Library) -> VideoDetail:
    return service.attach("collections", item_id, video_id)


@router.delete("/collections/{item_id}/videos/{video_id}", response_model=VideoDetail)
def remove_collection(item_id: str, video_id: str, service: Library) -> VideoDetail:
    return service.attach("collections", item_id, video_id, remove=True)


@router.get("/tags", response_model=list[NamedItem])
def tags(service: Library) -> list[NamedItem]:
    return service.organization("tags")


@router.post("/tags", response_model=NamedItem, status_code=201)
def create_tag(body: NameInput, service: Library) -> NamedItem:
    return service.organization("tags", body.name)


@router.post("/videos/{video_id}/tags/{item_id}", response_model=VideoDetail)
def add_tag(item_id: str, video_id: str, service: Library) -> VideoDetail:
    return service.attach("tags", item_id, video_id)


@router.delete("/videos/{video_id}/tags/{item_id}", response_model=VideoDetail)
def remove_tag(item_id: str, video_id: str, service: Library) -> VideoDetail:
    return service.attach("tags", item_id, video_id, remove=True)
