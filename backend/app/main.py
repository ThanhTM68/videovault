from fastapi import FastAPI

from app.api.v1.router import router
from app.core.config import Settings


def create_app() -> FastAPI:
    settings = Settings()
    application = FastAPI(title="VideoVault", version="0.1.0")
    application.state.settings = settings
    application.include_router(router)
    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = app.state.settings
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "development",
    )
