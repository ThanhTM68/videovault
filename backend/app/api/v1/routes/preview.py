from fastapi import APIRouter, Request

from app.schemas.preview import ResolveRequest, VideoPreview
from app.services.preview import PreviewService

router = APIRouter()


@router.post("/videos/resolve", response_model=VideoPreview)
def resolve_video(body: ResolveRequest, request: Request) -> VideoPreview:
    service: PreviewService = request.app.state.preview_service
    return service.resolve(body.url)
