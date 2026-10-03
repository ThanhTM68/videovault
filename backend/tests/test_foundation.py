import logging
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_settings
from app.application import create_app
from app.core.config import Settings
from app.core.logging import configure_logging


def test_settings_are_scoped_to_application(settings: Settings) -> None:
    other = Settings(_env_file=None, app_env="test", download_concurrency=7)
    for configured in (settings, other):
        application = create_app(configured, start_workers=False)

        @application.get("/api/v1/test-settings")
        def read_settings(current: Annotated[Settings, Depends(get_settings)]) -> dict[str, int]:
            return {"concurrency": current.download_concurrency}

        with TestClient(application) as client:
            response = client.get("/api/v1/test-settings")
        assert response.json() == {"concurrency": configured.download_concurrency}


def test_fastapi_settings_override(application: FastAPI) -> None:
    @application.get("/api/v1/test-settings")
    def read_settings(current: Annotated[Settings, Depends(get_settings)]) -> dict[str, int]:
        return {"concurrency": current.download_concurrency}

    application.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, download_concurrency=9
    )
    with TestClient(application) as client:
        assert client.get("/api/v1/test-settings").json() == {"concurrency": 9}


@pytest.mark.parametrize(
    ("environment", "level"),
    [("development", logging.DEBUG), ("test", logging.INFO), ("production", logging.INFO)],
)
def test_logging_level_and_idempotence(environment: str, level: int) -> None:
    configured = Settings(_env_file=None, app_env=environment)
    configure_logging(configured)
    logger = logging.getLogger("app")
    handler_count = len(logger.handlers)
    configure_logging(configured)
    assert logger.level == level
    assert len(logger.handlers) == handler_count
    assert logger.handlers[0].formatter is not None


def test_no_test_routes_in_default_application(settings: Settings) -> None:
    application = create_app(settings)
    assert set(application.openapi()["paths"]) == {
        "/api/v1/health",
        "/api/v1/sources/resolve",
        "/api/v1/sources/batch-download",
        "/api/v1/storage",
        "/api/v1/storage/google-drive/connect",
        "/api/v1/storage/google-drive/callback",
        "/api/v1/storage/google-drive/disconnect",
        "/api/v1/storage/google-drive/root",
        "/api/v1/videos/{video_id}/refresh-files",
        "/api/v1/downloads",
        "/api/v1/jobs",
        "/api/v1/jobs/{job_id}",
        "/api/v1/jobs/{job_id}/cancel",
        "/api/v1/jobs/{job_id}/retry",
        "/api/v1/queue/pause",
        "/api/v1/queue/resume",
        "/api/v1/queue",
        "/api/v1/videos/resolve",
        "/api/v1/videos",
        "/api/v1/videos/{video_id}",
        "/api/v1/videos/{video_id}/file",
        "/api/v1/videos/{video_id}/history",
        "/api/v1/videos/{video_id}/all",
        "/api/v1/videos/{video_id}/redownload",
        "/api/v1/history",
        "/api/v1/collections",
        "/api/v1/collections/{item_id}/videos/{video_id}",
        "/api/v1/tags",
        "/api/v1/videos/{video_id}/tags/{item_id}",
    }
