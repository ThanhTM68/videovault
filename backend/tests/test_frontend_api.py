from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select

from app.db.session import create_session_factory
from app.models import Job
from app.models.enums import Platform
from app.services.downloader.errors import AuthenticationRequiredError, UnsupportedPlatformError
from app.services.downloader.metadata import normalize_metadata
from tests.downloader_fixtures import FIXTURES, URL


def test_queue_read_is_authoritative_across_browser_sessions(application: FastAPI) -> None:
    with TestClient(application) as client:
        assert client.get("/api/v1/queue").json() == {"paused": False}
        client.post("/api/v1/queue/pause")
        with TestClient(application) as other:
            assert other.get("/api/v1/queue").json() == {"paused": True}
        assert client.post("/api/v1/queue/resume").json() == {"paused": False}
        assert client.get("/api/v1/queue").json() == {"paused": False}


def test_preview_projection_sanitizes_input_without_jobs_or_downloads(
    application: FastAPI, db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    downloader = application.state.preview_service.downloader
    resolve = MagicMock(
        return_value=normalize_metadata(FIXTURES["combined"], Platform.YOUTUBE, URL)
    )
    download = MagicMock()
    monkeypatch.setattr(downloader, "resolve", resolve)
    monkeypatch.setattr(downloader, "download", download)
    with TestClient(application) as client:
        response = client.post("/api/v1/videos/resolve", json={"url": URL + "&token=secret"})
    assert response.status_code == 200
    assert set(response.json()) == {
        "platform",
        "platform_video_id",
        "canonical_url",
        "title",
        "creator",
        "duration_seconds",
        "width",
        "height",
        "thumbnail_url",
        "video_id",
        "has_file",
        "has_download_history",
    }
    assert response.json()["platform"] == "youtube"
    resolve.assert_called_once_with(URL)
    download.assert_not_called()
    with create_session_factory(db_engine)() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0


@pytest.mark.parametrize("error", [AuthenticationRequiredError(), UnsupportedPlatformError()])
def test_preview_domain_failures_use_existing_envelope(
    application: FastAPI, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    monkeypatch.setattr(
        application.state.preview_service.downloader, "resolve", MagicMock(side_effect=error)
    )
    with TestClient(application) as client:
        response = client.post("/api/v1/videos/resolve", json={"url": URL})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == error.code


@pytest.mark.parametrize(
    "body",
    [
        {"url": "file:///private"},
        {"url": URL, "cookies": "secret"},
        {"url": "https://user:password@youtube.com/watch?v=id"},
    ],
)
def test_preview_invalid_input_never_resolves(
    application: FastAPI, monkeypatch: pytest.MonkeyPatch, body: dict
) -> None:
    resolve = MagicMock()
    monkeypatch.setattr(application.state.preview_service.downloader, "resolve", resolve)
    with TestClient(application) as client:
        response = client.post("/api/v1/videos/resolve", json=body)
    assert response.status_code == 422
    assert "secret" not in response.text and "password" not in response.text
    resolve.assert_not_called()
