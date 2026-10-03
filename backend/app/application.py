from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from app.api.error_handlers import register_exception_handlers
from app.api.v1.router import router
from app.core.config import Settings
from app.core.logging import configure_logging
from app.db.session import create_database_engine, create_session_factory
from app.services.downloader.service import DownloaderService
from app.services.preview import PreviewService
from app.services.queue.service import QueueService
from app.services.sources.adapters import SourceAdapterRegistry
from app.services.sources.service import SourceService
from app.workers.manager import WorkerManager


def create_app(
    settings: Settings | None = None,
    *,
    start_workers: bool = True,
    downloader: DownloaderService | None = None,
) -> FastAPI:
    settings = settings if settings is not None else Settings()
    configure_logging(settings)
    engine = create_database_engine(settings)
    sessions = create_session_factory(engine)
    queue = QueueService(sessions, downloader or DownloaderService(settings))
    manager = WorkerManager(queue, settings.download_concurrency, on_stopped=engine.dispose)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        try:
            if start_workers:
                await run_in_threadpool(manager.start)
            yield
        finally:
            if (
                start_workers
                and manager.supervisor is not None
                and manager.supervisor.ident is not None
            ):
                await run_in_threadpool(manager.stop)
            else:
                engine.dispose()

    application = FastAPI(title="VideoVault", version="0.1.0", lifespan=lifespan)
    application.state.settings = settings
    application.state.engine = engine
    application.state.session_factory = sessions
    application.state.worker_manager = manager
    application.state.preview_service = PreviewService(queue.downloader, queue.library)
    application.state.source_service = SourceService(queue, SourceAdapterRegistry())
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
    register_exception_handlers(application)
    application.include_router(router)
    return application
