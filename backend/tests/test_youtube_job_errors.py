"""Real API/worker persistence under deterministic anonymous YouTube failures."""

import json
import time
from copy import deepcopy
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from yt_dlp import dependencies
from yt_dlp.utils import DownloadError, ExtractorError

from app.application import create_app
from app.core.config import Settings
from app.models import Download, Job, MediaFile, Video
from app.models.enums import DownloadStatus
from app.services.downloader import runtime, ytdlp
from app.workers.download_worker import execute_download
from tests.downloader_fixtures import FIXTURES, URL


def blocked_error() -> DownloadError:
    cause = ExtractorError("Sign in to confirm you're not a bot private-secret-marker")
    return DownloadError(str(cause), exc_info=(type(cause), cause, None))


@pytest.fixture
def extractor(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    # Runtime configuration itself is separately tested with the real pinned SDK.
    # This boundary double keeps the API/worker suite independent of installed Node.
    monkeypatch.setattr(
        ytdlp,
        "youtube_runtime_options",
        lambda: {"js_runtimes": {"node": {"path": "demo-node"}}, "remote_components": []},
    )
    instance = MagicMock()
    instance.__enter__.return_value = instance
    instance.extract_info.return_value = deepcopy(FIXTURES["combined"]) | {
        "extractor_key": "Youtube"
    }
    monkeypatch.setattr(ytdlp.yt_dlp, "YoutubeDL", MagicMock(return_value=instance))
    return instance


def assert_no_success(app: FastAPI, *, events: int, videos: int) -> None:
    with app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1
        assert session.scalar(select(func.count()).select_from(Video)) == videos
        assert session.scalar(select(func.count()).select_from(Download)) == events
        assert session.scalar(select(func.count()).select_from(MediaFile)) == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(Download)
                .where(Download.status == DownloadStatus.COMPLETED)
            )
            == 0
        )


def wait_failed(client: TestClient, identity: str, attempt: int) -> dict:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        response = client.get("/api/v1/jobs/" + identity)
        assert response.status_code == 200
        row = response.json()
        if row["status"] == "failed" and row["attempt_count"] == attempt:
            return row
        Event().wait(0.01)
    pytest.fail("The ordinary worker did not persist its terminal failed state")


def test_preview_bot_response_passes_through_real_wrapper_safely(
    settings: Settings, db_engine, extractor: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    extractor.extract_info.side_effect = blocked_error()
    app = create_app(settings, start_workers=False)
    with TestClient(app) as client:
        response = client.post("/api/v1/videos/resolve", json={"url": URL})
        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "PLATFORM_ACCESS_BLOCKED"
        assert "may still be public" in error["message"] and error["details"] == {}
        assert "authentication or access permission" not in response.text
        assert client.get("/api/v1/health").json() == {"status": "ok"}
    with app.state.session_factory() as session:
        for model in (Job, Video, Download, MediaFile):
            assert session.scalar(select(func.count()).select_from(model)) == 0
    assert "private-secret-marker" not in response.text + caplog.text
    extractor.process_ie_result.assert_not_called()


@pytest.mark.parametrize("missing", ["node", "ejs"])
def test_missing_runtime_preview_does_not_break_startup_or_leave_jobs(
    settings: Settings,
    db_engine,
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    original_which = runtime.shutil.which
    monkeypatch.setattr(
        runtime.shutil,
        "which",
        lambda name: (
            (None if missing == "node" else "demo-node") if name == "node" else original_which(name)
        ),
    )
    if missing == "ejs":
        monkeypatch.setattr(
            runtime.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="v22.0.0\n")
        )
        monkeypatch.setattr(dependencies, "yt_dlp_ejs", None)
    sdk_factory = MagicMock()
    monkeypatch.setattr(ytdlp.yt_dlp, "YoutubeDL", sdk_factory)
    app = create_app(settings, start_workers=False)
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/storage").status_code == 200
        response = client.post("/api/v1/videos/resolve", json={"url": URL})
        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "EXTRACTOR_RUNTIME_UNAVAILABLE"
        assert error["details"] == {}
        assert "demo-node" not in response.text and "AUTHENTICATION_REQUIRED" not in response.text
        assert client.get("/api/v1/health").status_code == 200
    sdk_factory.assert_not_called()
    with app.state.session_factory() as session:
        for model in (Job, Video, Download, MediaFile):
            assert session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize("failure", ["blocked", "runtime"])
def test_real_workers_fail_once_per_manual_retry_and_honor_attempt_limit(
    settings: Settings,
    db_engine,
    extractor: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failure: str,
) -> None:
    extractor.extract_info.side_effect = blocked_error()
    probe = extractor.extract_info
    code = "PLATFORM_ACCESS_BLOCKED"
    if failure == "runtime":
        original_which = runtime.shutil.which
        monkeypatch.setattr(
            runtime.shutil, "which", lambda name: None if name == "node" else original_which(name)
        )
        probe = MagicMock(wraps=runtime.youtube_runtime_options)
        monkeypatch.setattr(ytdlp, "youtube_runtime_options", probe)
        code = "EXTRACTOR_RUNTIME_UNAVAILABLE"
    app = create_app(settings)
    manager = app.state.worker_manager
    manager.poll_seconds = 0.01
    manager.heartbeat_seconds = 0.02
    with TestClient(app) as client:
        submitted = client.post("/api/v1/downloads", json={"urls": [URL]})
        assert submitted.status_code == 202
        identity = submitted.json()["jobs"][0]["id"]
        for attempt in range(1, 4):
            row = wait_failed(client, identity, attempt)
            assert row["max_attempts"] == 3 and row["progress_percent"] < 100
            assert row["completed_at"] is not None
            assert row["error"]["code"] == code
            assert "authentication or access permission" not in row["error"]["message"]
            assert "private-secret-marker" not in json.dumps(row)
            # Let multiple ordinary claim cycles pass: no automatic retry storm.
            Event().wait(0.06)
            assert probe.call_count == attempt
            assert len(manager._active) == 0
            assert_no_success(app, events=0, videos=0)
            if attempt < 3:
                assert client.post("/api/v1/queue/pause").status_code == 200
                retried = client.post(f"/api/v1/jobs/{identity}/retry")
                assert retried.status_code == 200 and retried.json()["id"] == identity
                assert retried.json()["status"] == "queued"
                # A second click cannot schedule another active attempt.
                assert client.post(f"/api/v1/jobs/{identity}/retry").status_code == 409
                assert client.post("/api/v1/queue/resume").status_code == 200
        exhausted = client.post(f"/api/v1/jobs/{identity}/retry")
        assert exhausted.status_code == 409
        assert client.get("/api/v1/jobs/" + identity).json()["attempt_count"] == 3
        assert client.get("/api/v1/health").status_code == 200
        assert len(manager.threads) == settings.download_concurrency
    assert all(not thread.is_alive() for thread in manager.threads)
    assert not manager.supervisor.is_alive()
    assert not list(settings.temp_storage_root.glob("*"))
    assert "private-secret-marker" not in caplog.text
    extractor.process_ie_result.assert_not_called()
    if failure == "runtime":
        extractor.extract_info.assert_not_called()


@pytest.mark.parametrize("stage", ["download_resolve", "download_extract", "media_download"])
def test_block_during_download_records_a_truthful_failed_event_and_cleans_temp(
    settings: Settings,
    db_engine,
    extractor: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    stage: str,
) -> None:
    info = deepcopy(extractor.extract_info.return_value)
    if stage == "download_resolve":
        extractor.extract_info.side_effect = [info, blocked_error()]
    elif stage == "download_extract":
        extractor.extract_info.side_effect = [info, info, blocked_error()]
    else:
        extractor.extract_info.return_value = info
        extractor.process_ie_result.side_effect = blocked_error()
    monkeypatch.setattr(ytdlp, "require_tool", lambda name: "demo-ffmpeg")
    app = create_app(settings, start_workers=False)
    queue = app.state.worker_manager.queue
    with TestClient(app) as client:
        submitted = client.post("/api/v1/downloads", json={"urls": [URL]})
        identity = submitted.json()["jobs"][0]["id"]
        claim = queue.claim()
        assert claim is not None and claim.id == identity
        execute_download(queue, claim, Event())
        row = client.get("/api/v1/jobs/" + identity).json()
        assert row["status"] == "failed" and row["attempt_count"] == 1
        assert row["error"]["code"] == "PLATFORM_ACCESS_BLOCKED"
        assert row["progress_percent"] < 100
        history = client.get("/api/v1/history").json()
        assert history["total"] == 1
        event = history["items"][0]
        assert event["status"] == "failed" and event["job_id"] == identity
        assert event["attempt_number"] == 1 and event["completed_at"] is not None
        assert event["failure_code"] == "PLATFORM_ACCESS_BLOCKED"
        assert "may still be public" in event["failure_message"]
        assert "private-secret-marker" not in json.dumps(history) + caplog.text
        library = client.get("/api/v1/videos").json()
        assert library["total"] == 1
        assert not library["items"][0]["has_file"]
        assert not library["items"][0]["has_download_history"]
        assert_no_success(app, events=1, videos=1)
        assert queue.claim() is None
    assert not list(settings.temp_storage_root.glob("*"))
    assert not list(settings.local_storage_root.glob("**/*.mp4"))
    if stage != "media_download":
        extractor.process_ie_result.assert_not_called()
