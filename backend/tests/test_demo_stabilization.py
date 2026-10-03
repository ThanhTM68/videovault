import importlib.util
import json
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest
from google.oauth2.credentials import Credentials

from app.models.enums import DownloadStatus, JobStatus, StorageProvider
from app.repositories.storage import StorageAccountRepository
from app.services.queue.models import DownloadPayload
from app.services.storage.credentials import CredentialFile
from app.services.storage.errors import StorageError
from app.workers.download_worker import execute_download
from tests.storage_fixtures import credentials

SPEC = importlib.util.spec_from_file_location(
    "demo_stabilization", Path(__file__).resolve().parents[2] / "scripts/demo_stabilization.py"
)
assert SPEC is not None and SPEC.loader is not None
demo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(demo)


def test_demo_root_refuses_existing_unmarked_directory(tmp_path):
    root = tmp_path / "existing-development-data"
    root.mkdir()
    original = root / "unrelated.txt"
    original.write_text("Preserve this data", encoding="utf-8")
    with pytest.raises(ValueError, match="without the demo marker"):
        demo.prepare_root(root)
    assert original.read_text(encoding="utf-8") == "Preserve this data"
    assert not (root / demo.MARKER).exists()


@pytest.mark.parametrize("file_name", ["demo.db", "fake-drive-fault.json"])
def test_demo_root_refuses_linked_runtime_path(tmp_path, monkeypatch, file_name):
    root = demo.prepare_root(tmp_path / "demo")
    database = root / file_name
    database.write_text("Preserve this linked target", encoding="utf-8")
    original_lstat = Path.lstat

    def reparse_lstat(path, *args, **kwargs):
        if path == database:
            return SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0x400)
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", reparse_lstat)
    with pytest.raises(ValueError, match="symlinks or reparse points"):
        demo.prepare_root(root)
    assert database.read_text(encoding="utf-8") == "Preserve this linked target"


def test_demo_settings_ignore_project_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_PROVIDER", "google_drive")
    monkeypatch.setenv("DOWNLOAD_CONCURRENCY", "999")
    app = demo.build_demo(tmp_path / "demo")
    try:
        assert app.state.settings.storage_provider == StorageProvider.LOCAL
        assert app.state.worker_manager.concurrency == 3
    finally:
        app.state.engine.dispose()


def test_demo_restart_seeding_does_not_execute_pending_jobs(tmp_path):
    root = tmp_path / "demo"
    first = demo.build_demo(root, seed_library=1)
    queue = first.state.worker_manager.queue
    pending = queue.submit([DownloadPayload(url=demo.fixture_url("demo0000002"), max_height=1080)])[
        0
    ]
    first.state.engine.dispose()
    second = demo.build_demo(root, seed_library=1)
    try:
        job = second.state.worker_manager.queue.get(pending.id)
        assert job.status == JobStatus.QUEUED and job.attempt_count == 0
        assert second.state.worker_manager.queue.list().total == 2
        assert second.state.demo_adapter.transfers == 0
    finally:
        second.state.engine.dispose()


def test_demo_refuses_unknown_credentials_without_modifying_them(tmp_path):
    root = demo.prepare_root(tmp_path / "demo")
    tokens = CredentialFile(root / "private-auth")
    unknown = json.loads(credentials().to_json()) | {"token": "foreign-synthetic-credential"}
    tokens.write(unknown)
    original = tokens.path.read_bytes()
    with pytest.raises(ValueError, match="known demo"):
        demo.build_demo(root, fake_drive=True)
    assert tokens.path.read_bytes() == original


def test_demo_refuses_unknown_drive_account_without_rebinding(tmp_path):
    root = tmp_path / "demo"
    first = demo.build_demo(root, fake_drive=True)
    queue = first.state.worker_manager.queue
    with queue.sessions.begin() as session:
        StorageAccountRepository(session).bind("foreign-synthetic-account", "Other fixture")
    first.state.engine.dispose()
    with pytest.raises(ValueError, match="non-demo Drive account"):
        demo.build_demo(root, fake_drive=True)


def test_expired_fake_credentials_never_use_google_refresh(tmp_path, monkeypatch):
    app = demo.build_demo(tmp_path / "demo", fake_drive=True, connect_fake_drive=True)
    connection = app.state.worker_manager.queue.storage.connection
    expired = credentials()
    expired.expiry = (datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None)
    connection.tokens.write(json.loads(expired.to_json()))

    def prohibit_real_refresh(*args, **kwargs):
        pytest.fail("The offline demo attempted a Google token refresh")

    monkeypatch.setattr(Credentials, "refresh", prohibit_real_refresh)
    try:
        with connection.client() as client:
            assert client is app.state.demo_drive
        assert connection.status().connected
        connection.disconnect()
        assert not connection.status().connected
    finally:
        app.state.engine.dispose()


@pytest.mark.parametrize("container", ["mp4", "mkv", "webm"])
@pytest.mark.parametrize("audio", [True, False])
def test_demo_generates_real_media_for_supported_options(tmp_path, container, audio):
    app = demo.build_demo(tmp_path / "demo")
    app.state.demo_adapter.seed_mode = True
    queue = app.state.worker_manager.queue
    try:
        job = queue.submit(
            [
                DownloadPayload(
                    url=demo.fixture_url(demo.NORMAL_ID),
                    max_height=1080,
                    preferred_container=container,
                    audio_enabled=audio,
                )
            ]
        )[0]
        claim = queue.claim()
        execute_download(queue, claim, Event())
        assert queue.get(job.id).status == JobStatus.COMPLETED
        videos = queue.library.list(page=1, page_size=25).items
        assert len(videos) == 1 and videos[0].has_file and videos[0].has_download_history
        detail = queue.library.detail(videos[0].id)
        assert detail.files[0].container == container
        assert len(detail.files[0].sha256) == 64
        assert list(app.state.settings.local_storage_root.glob("*." + container))
    finally:
        app.state.engine.dispose()


def test_demo_upload_permission_fault_retains_failure_and_recovers_on_retry(tmp_path):
    root = tmp_path / "demo"
    app = demo.build_demo(root, fake_drive=True, connect_fake_drive=True)
    app.state.demo_adapter.seed_mode = True
    queue = app.state.worker_manager.queue
    fault = root / "fake-drive-fault.json"
    fault.write_text(json.dumps({"upload": 403}), encoding="utf-8")
    try:
        job = queue.submit(
            [
                DownloadPayload(
                    url=demo.fixture_url(demo.NORMAL_ID),
                    max_height=1080,
                    storage_target=StorageProvider.GOOGLE_DRIVE,
                )
            ]
        )[0]
        execute_download(queue, queue.claim(), Event())
        failed = queue.get(job.id)
        assert failed.status == JobStatus.FAILED
        assert failed.error is not None and failed.error.code == "STORAGE_PERMISSION_DENIED"
        history = queue.library.history(page=1, page_size=25).items
        assert len(history) == 1 and history[0].status == DownloadStatus.FAILED
        video = queue.library.list(page=1, page_size=25).items[0]
        assert not video.has_file and not video.has_download_history
        assert not list(app.state.settings.temp_storage_root.iterdir())
        assert fault.exists()  # Faults persist until the demo operator removes them.
        fault.unlink()
        queue.retry(job.id)
        execute_download(queue, queue.claim(), Event())
        assert queue.get(job.id).status == JobStatus.COMPLETED
        assert queue.get(job.id).attempt_count == 2
        history = queue.library.history(page=1, page_size=25).items
        assert {item.status for item in history} == {
            DownloadStatus.FAILED,
            DownloadStatus.COMPLETED,
        }
        assert queue.library.detail(video.id).has_file
        assert list(app.state.demo_drive.media_root.glob("*.bin"))
        assert not list(app.state.settings.temp_storage_root.iterdir())
    finally:
        app.state.engine.dispose()


def test_demo_delete_permission_fault_reports_truthful_partial_progress(tmp_path):
    root = tmp_path / "demo"
    app = demo.build_demo(root, fake_drive=True, connect_fake_drive=True)
    app.state.demo_adapter.seed_mode = True
    queue = app.state.worker_manager.queue
    try:
        for provider in (StorageProvider.GOOGLE_DRIVE, StorageProvider.LOCAL):
            job = queue.submit(
                [
                    DownloadPayload(
                        url=demo.fixture_url(demo.NORMAL_ID),
                        max_height=1080,
                        storage_target=provider,
                        force=True,
                    )
                ]
            )[0]
            execute_download(queue, queue.claim(), Event())
            assert queue.get(job.id).status == JobStatus.COMPLETED
        video = queue.library.list(page=1, page_size=25).items[0]
        fault = root / "fake-drive-fault.json"
        fault.write_text(json.dumps({"delete": 403}), encoding="utf-8")
        with pytest.raises(StorageError) as failure:
            queue.library.destroy(video.id, "all")
        assert failure.value.code == "STORAGE_PERMISSION_DENIED"
        detail = queue.library.detail(video.id)
        assert detail.has_file and detail.has_download_history and len(detail.history) == 2
        assert {(item.storage_provider, item.state) for item in detail.files} == {
            (StorageProvider.LOCAL, "deleted"),
            (StorageProvider.GOOGLE_DRIVE, "stored"),
        }
        assert not list(app.state.settings.local_storage_root.glob("*.mp4"))
        assert list(app.state.demo_drive.media_root.glob("*.bin"))
        fault.unlink()
        result = queue.library.destroy(video.id, "all")
        assert not result.has_file and not result.has_download_history
        assert not list(app.state.demo_drive.media_root.glob("*.bin"))
    finally:
        app.state.engine.dispose()


@pytest.mark.parametrize("payload", ['{"delete":', '"' + "x" * 1024 + '"', '{"unexpected":403}'])
def test_demo_fault_configuration_fails_safely_when_invalid(tmp_path, payload):
    root = demo.prepare_root(tmp_path / "demo")
    drive = demo.PersistentDrive(root)
    drive.fault.write_text(payload, encoding="utf-8")
    with pytest.raises(StorageError) as failure:
        drive.network("delete")
    assert failure.value.code == "STORAGE_UNAVAILABLE"
