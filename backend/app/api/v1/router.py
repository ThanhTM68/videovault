from fastapi import APIRouter

from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.queue import router as queue_router

router = APIRouter(prefix="/api/v1")
router.include_router(health_router)
router.include_router(queue_router)
