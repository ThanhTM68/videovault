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
        application = create_app(configured)

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
    assert set(application.openapi()["paths"]) == {"/api/v1/health"}
