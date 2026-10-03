from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.schemas.sources import (
    BatchDownloadRequest,
    BatchDownloadResult,
    SourcePreview,
    SourceResolveRequest,
)
from app.services.sources.service import SourceService

router = APIRouter(prefix="/sources")


def sources(request: Request) -> SourceService:
    return request.app.state.source_service


Sources = Annotated[SourceService, Depends(sources)]


@router.post("/resolve", response_model=SourcePreview)
def resolve(body: SourceResolveRequest, service: Sources) -> SourcePreview:
    return service.resolve(body)


@router.post("/batch-download", response_model=BatchDownloadResult, status_code=202)
def submit(body: BatchDownloadRequest, service: Sources, request: Request) -> BatchDownloadResult:
    result = service.submit(body)
    if result.created_count:
        request.app.state.worker_manager.notify()
    return result
