from fastapi import APIRouter

from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.library import router as library_router
from app.api.v1.routes.preview import router as preview_router
from app.api.v1.routes.queue import router as queue_router
from app.api.v1.routes.storage import router as storage_router

router = APIRouter(prefix="/api/v1")
router.include_router(health_router)
router.include_router(preview_router)
router.include_router(queue_router)
router.include_router(library_router)
router.include_router(storage_router)
