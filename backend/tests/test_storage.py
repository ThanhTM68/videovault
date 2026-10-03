import hashlib
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi.testclient import TestClient
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from pydantic import SecretStr
from sqlalchemy import select

from app.application import create_app
from app.db.session import create_session_factory
from app.models import MediaFile, StorageAccount
from app.models.enums import JobStatus as S
from app.models.enums import Platform
from app.models.enums import StorageProvider as P
from app.repositories.library import LibraryRepository
from app.services.downloader.service import DownloaderService
from app.services.queue.models import DownloadPayload
from app.services.queue.service import QueueService
from app.services.storage.credentials import CredentialFile
from app.services.storage.errors import StorageError
from app.services.storage.google_client import call_google
from app.workers.download_worker import execute_download
from tests.downloader_fixtures import URL
from tests.storage_fixtures import FakeDrive, connect, http_error
from tests.test_library import only_video
from tests.test_queue import ControlledAdapter


@pytest.fixture
def drive_queue(db_engine, settings, local_media):
    configured = settings.model_copy(
        update={
            "google_drive_client_id": "test-client",
            "google_drive_client_secret": SecretStr("test-client-secret"),
            "google_drive_redirect_uri": "http://127.0.0.1:8000/api/v1/storage/google-drive/callback",
        }
    )
    adapter = ControlledAdapter(local_media)
    adapter.release.set()
    queue = QueueService(
        create_session_factory(db_engine),
        DownloaderService(configured, {Platform.YOUTUBE: adapter}),
    )
    drive = FakeDrive(db_engine)
    connect(queue.storage, drive)
    return queue, drive


def run(queue, target=P.GOOGLE_DRIVE, force=False, cancellation=None):
    job = queue.submit(
        [DownloadPayload(url=URL, max_height=1080, storage_target=target, force=force)]
    )[0]
    claim = queue.claim()
    assert claim.id == job.id
    execute_download(queue, claim, cancellation or Event())
    return queue.get(job.id)


def media(drive):
    return [
        item
        for item in drive.objects.values()
        if item.get("appProperties", {}).get("videovault_kind") == "media"
    ]


def test_upload_hash_db_temp_commit_order_and_no_network_in_list(
    drive_queue, local_media, monkeypatch
):
    queue, drive = drive_queue
    original = LibraryRepository.save_result

    def save(repo, *args):
        assert len(media(drive)) == 1
        assert args[1].path.exists()
        original(repo, *args)

    monkeypatch.setattr(LibraryRepository, "save_result", save)
    assert run(queue).status == S.COMPLETED
    assert drive.uploaded_bytes == local_media.read_bytes()
    with queue.sessions() as session:
        row = session.scalar(select(MediaFile))
        assert row.storage_provider == P.GOOGLE_DRIVE
        assert row.sha256 == hashlib.sha256(local_media.read_bytes()).hexdigest()
        assert row.storage_key == media(drive)[0]["id"]
    assert not list(queue.downloader.settings.temp_storage_root.iterdir())
    calls = list(drive.calls)
    video = only_video(queue)
    detail = queue.library.detail(video.id)
    assert detail.files[0].state == "stored" and detail.has_file
    assert detail.files[0].storage_provider == P.GOOGLE_DRIVE
    assert drive.calls == calls
    assert "storage_key" not in detail.model_dump_json()


def test_cross_provider_dedup_force_and_folder_reuse(drive_queue):
    queue, drive = drive_queue
    assert run(queue, P.LOCAL).status == S.COMPLETED
    assert run(queue).status == S.SKIPPED_DUPLICATE
    assert run(queue, force=True).status == S.COMPLETED
    folders = drive.calls.count("create-folder")
    assert run(queue, force=True).status == S.COMPLETED
    assert drive.calls.count("create-folder") == folders == 4
    assert len(media(drive)) == 2
    assert len(queue.library.detail(only_video(queue).id).files) == 3
    assert all(" in parents" in query and "trashed = false" in query for query in drive.queries)


@pytest.mark.parametrize("mode", ["history", "file", "all"])
def test_mixed_delete_semantics(drive_queue, mode):
    queue, drive = drive_queue
    run(queue, P.LOCAL)
    run(queue, force=True)
    detail = queue.library.destroy(only_video(queue).id, mode)
    assert detail.has_download_history == (mode == "file")
    assert detail.has_file == (mode == "history")
    assert bool(media(drive)) == (mode == "history")


def test_partial_mixed_delete_keeps_history_and_marks_success(drive_queue):
    queue, drive = drive_queue
    run(queue)
    run(queue, P.LOCAL, force=True)
    drive.errors["delete"] = [http_error(403)]
    with pytest.raises(StorageError):
        queue.library.destroy(only_video(queue).id, "all")
    detail = queue.library.detail(only_video(queue).id)
    assert detail.has_download_history and len(detail.history) == 2
    assert any(file.state == "deleted" for file in detail.files)
    assert len(media(drive)) == 1


@pytest.mark.parametrize("failure", ["db", "cancel", "upload"])
def test_failed_completion_compensates_new_object(drive_queue, monkeypatch, failure):
    queue, drive = drive_queue
    signal = Event()
    if failure == "db":

        def fail(*args):
            raise RuntimeError("private-data-not-for-logs")

        monkeypatch.setattr(LibraryRepository, "save_result", fail)
    elif failure == "cancel":
        drive.after_upload = signal.set
    else:
        drive.errors["upload"] = [http_error(403)]
    job = run(queue, cancellation=signal)
    assert job.status == (S.CANCELLED if failure == "cancel" else S.FAILED)
    assert not media(drive)
    assert not only_video(queue).has_download_history
    assert not only_video(queue).has_file
    assert not list(queue.downloader.settings.temp_storage_root.iterdir())


def test_orphan_warning_is_safe_and_never_completed(drive_queue, monkeypatch, caplog):
    queue, drive = drive_queue

    def fail(*args):
        raise RuntimeError("test-refresh-token")

    monkeypatch.setattr(LibraryRepository, "save_result", fail)
    drive.errors["delete"] = [http_error(403)]
    assert run(queue).status == S.FAILED
    assert len(media(drive)) == 1 and "orphan possible" in caplog.text
    assert "test-refresh-token" not in caplog.text


@pytest.mark.parametrize("remote", ["missing", "trashed", "permission", "auth"])
def test_targeted_refresh_distinguishes_missing_and_unavailable(drive_queue, remote):
    queue, drive = drive_queue
    run(queue)
    item = media(drive)[0]
    if remote == "missing":
        del drive.objects[item["id"]]
    elif remote == "trashed":
        item["trashed"] = True
    else:
        drive.errors["get"] = [http_error(403 if remote == "permission" else 401)]
    detail = queue.library.detail(only_video(queue).id, verify_remote=True)
    assert detail.files[0].state == (
        "missing" if remote in {"missing", "trashed"} else "unavailable"
    )
    with queue.sessions() as session:
        assert (session.scalar(select(MediaFile)).missing_at is not None) == (
            remote in {"missing", "trashed"}
        )
    assert detail.has_download_history


def test_status_and_submission_do_not_wait_for_upload_lease(drive_queue):
    queue, _ = drive_queue
    with queue.storage.connection.lease(), ThreadPoolExecutor() as executor:
        result = executor.submit(
            queue.submit, [DownloadPayload(url=URL, max_height=1080, storage_target=P.GOOGLE_DRIVE)]
        )
        assert result.result(timeout=1)[0].status == S.QUEUED


def test_disconnect_preserves_records_reconnect_rejects_other_account(drive_queue):
    queue, drive = drive_queue
    run(queue)
    connection = queue.storage.connection
    connection.disconnect()
    assert not connection.tokens.path.exists()
    assert not connection.status().connected
    assert only_video(queue).has_download_history and media(drive)
    drive.identity = "different-account"
    connection.start()
    with pytest.raises(StorageError, match="original"):
        connection.callback(next(iter(connection.states)), "test-code", None)
    assert not connection.status().connected


@pytest.mark.parametrize("invalid", ["unknown", "expired", "denied", "replayed"])
def test_oauth_state_one_use_expiry_denial(drive_queue, invalid):
    queue, _ = drive_queue
    connection = queue.storage.connection
    connection.start()
    state = next(iter(connection.states))
    if invalid == "unknown":
        state = "unknown"
    elif invalid == "expired":
        connection.clock = lambda: float("inf")
    elif invalid == "replayed":
        connection.callback(state, "code", None)
    with pytest.raises(StorageError) as error:
        connection.callback(state, "code", "access_denied" if invalid == "denied" else None)
    assert error.value.code == ("OAUTH_DENIED" if invalid == "denied" else "OAUTH_STATE_INVALID")
    assert state not in connection.states


def test_token_only_private_and_refresh_revocation(drive_queue, monkeypatch):
    queue, _ = drive_queue
    connection = queue.storage.connection
    data = connection.tokens.read()
    data["expiry"] = "2000-01-01T00:00:00Z"
    connection.tokens.write(data)

    def refresh(self, request):
        self.token = "refreshed-test-token"

    monkeypatch.setattr(Credentials, "refresh", refresh)
    with connection.client():
        pass
    assert connection.tokens.read()["token"] == "refreshed-test-token"

    def revoke(*args):
        raise RefreshError("do-not-log-this-secret")

    monkeypatch.setattr(Credentials, "refresh", revoke)
    with pytest.raises(StorageError) as error, connection.client():
        pass
    assert error.value.code == "STORAGE_NOT_CONNECTED"
    assert not connection.tokens.path.exists()
    with queue.sessions() as session:
        row = session.scalar(select(StorageAccount))
        assert row.config_json == {"root_folder_id": "root-folder"}


def test_private_file_atomic_and_corruption(tmp_path):
    file = CredentialFile(tmp_path / "private")
    file.write({"token": "fake"})
    assert file.read() == {"token": "fake"}
    assert list(file.path.parent.iterdir()) == [file.path]
    file.path.write_text("not-json")
    with pytest.raises(StorageError):
        file.read()


@pytest.mark.parametrize("status", [429, 500, 503, 403])
def test_bounded_transient_retry(monkeypatch, status):
    waits = []
    monkeypatch.setattr(Event, "wait", lambda self, delay: waits.append(delay) or False)
    calls = []

    def action():
        calls.append(1)
        raise http_error(status, "rateLimitExceeded")

    with pytest.raises(StorageError):
        call_google(action)
    assert len(calls) == 4 and waits == [1, 2, 4]


def test_unconfigured_startup_and_submission(settings, db_engine):
    app = create_app(settings, start_workers=False)
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        response = client.get("/api/v1/storage")
        assert response.json()["default_target"] == "local"
        assert not response.json()["providers"][1]["configured"]
        failed = client.post(
            "/api/v1/downloads", json={"urls": [URL], "storage_target": "google_drive"}
        )
        assert failed.status_code == 400
        assert failed.json()["error"]["code"] == "STORAGE_NOT_CONFIGURED"
        assert client.post("/api/v1/downloads", json={"urls": [URL]}).status_code == 202


def test_storage_api_oauth_safe_redirect_default_target_and_root(drive_queue, caplog):
    queue, drive = drive_queue
    settings = queue.downloader.settings.model_copy(update={"storage_provider": P.GOOGLE_DRIVE})
    app = create_app(settings, start_workers=False)
    storage = app.state.worker_manager.queue.storage
    storage.connection.client_factory = queue.storage.connection.client_factory
    storage.connection.flow_factory = queue.storage.connection.flow_factory
    with TestClient(app) as client:
        assert client.get("/api/v1/storage").json()["default_target"] == "google_drive"
        created = client.post("/api/v1/downloads", json={"urls": [URL]})
        assert created.status_code == 202
        claim = app.state.worker_manager.queue.claim()
        assert claim.payload["storage_target"] == "google_drive"
        assert (
            client.put(
                "/api/v1/storage/google-drive/root", json={"folder_id": "../bad"}
            ).status_code
            == 422
        )
        assert (
            client.put(
                "/api/v1/storage/google-drive/root", json={"folder_id": "root-folder"}
            ).status_code
            == 200
        )
        assert client.post("/api/v1/storage/google-drive/root", json={}).status_code == 201
        assert (
            client.post(
                "/api/v1/storage/google-drive/connect", json={"client_secret": "secret"}
            ).status_code
            == 422
        )
        assert client.post("/api/v1/storage/google-drive/connect", json={}).status_code == 200
        state = next(iter(storage.connection.states))
        with caplog.at_level("INFO"):
            result = client.get(
                "/api/v1/storage/google-drive/callback",
                params={"state": state, "code": "sensitive-auth-code"},
                follow_redirects=False,
            )
        assert result.status_code == 303 and result.headers["location"].endswith("drive=connected")
        assert result.headers["cache-control"] == "no-store"
        assert "sensitive-auth-code" not in caplog.text and state not in caplog.text
        assert "test-refresh-token" not in client.get("/api/v1/storage").text
        failed = client.get(
            "/api/v1/storage/google-drive/callback?state=bad&code=private", follow_redirects=False
        )
        assert "OAUTH_STATE_INVALID" in failed.headers["location"]
        assert (
            client.post("/api/v1/storage/google-drive/disconnect", json={}).json()["providers"][1][
                "connected"
            ]
            is False
        )


@pytest.mark.parametrize("invalid", ["missing", "trashed", "readonly", "not-folder"])
def test_invalid_root_does_not_change_configuration(drive_queue, invalid):
    queue, drive = drive_queue
    item = drive.objects["root-folder"].copy()
    item["id"] = "invalid-root"
    if invalid != "missing":
        drive.objects["invalid-root"] = item
    if invalid == "trashed":
        item["trashed"] = True
    if invalid == "readonly":
        item["capabilities"] = {"canAddChildren": False}
    if invalid == "not-folder":
        item["mimeType"] = "video/mp4"
    with pytest.raises(StorageError) as error:
        queue.storage.drive.set_root("invalid-root")
    assert error.value.code == "STORAGE_ROOT_INVALID"
    assert queue.storage.connection.status().root_folder_id == "root-folder"


def test_root_reuse_duplicate_resolution_and_delete_ownership(drive_queue):
    queue, drive = drive_queue
    assert queue.storage.drive.set_root().id == "root-folder"
    drive.objects["a-root"] = drive.objects["root-folder"] | {"id": "a-root"}
    assert queue.storage.drive.set_root().id == "a-root"
    with pytest.raises(StorageError) as error:
        queue.storage.drive.delete("root-folder")
    assert error.value.code == "STORAGE_UNMANAGED_OBJECT"
    assert "root-folder" in drive.objects
    queue.storage.drive.delete("missing")
    assert not queue.storage.drive.exists("missing")


def test_upload_progress_cancel_between_chunks_and_cancel_before_put(drive_queue, monkeypatch):
    queue, drive = drive_queue
    signal = Event()
    original = queue.progress

    def progress(claim, state, phase, percent):
        original(claim, state, phase, percent)
        if state == S.UPLOADING:
            assert percent < 100
            if percent > 0:
                assert queue.get(claim.id).status == S.UPLOADING
                signal.set()

    monkeypatch.setattr(queue, "progress", progress)
    assert run(queue, cancellation=signal).status == S.CANCELLED
    assert not media(drive)
    drive.calls.clear()
    assert run(queue, cancellation=signal).status == S.CANCELLED
    assert not drive.calls


def test_disconnected_drive_prevalidates_all_before_local_delete(drive_queue):
    queue, drive = drive_queue
    run(queue)
    run(queue, P.LOCAL, force=True)
    queue.storage.connection.disconnect()
    with pytest.raises(StorageError):
        queue.library.destroy(only_video(queue).id, "all")
    detail = queue.library.detail(only_video(queue).id)
    assert all(file.state != "deleted" for file in detail.files)
    assert detail.has_file and detail.has_download_history and media(drive)


def test_oauth_pkce_real_flow_and_state_bounded(drive_queue):
    from urllib.parse import parse_qs, urlsplit

    from google_auth_oauthlib.flow import Flow

    queue, _ = drive_queue
    connection = queue.storage.connection
    connection.flow_factory = Flow.from_client_config
    for _ in range(35):
        url = connection.start()
    query = parse_qs(urlsplit(url).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["scope"] == ["https://www.googleapis.com/auth/drive.file"]
    assert "client_secret" not in query and len(connection.states) == 32
    assert len(query["state"][0]) >= 40


def test_oauth_failed_db_bind_restores_private_credentials(drive_queue, monkeypatch):
    from app.repositories.storage import StorageAccountRepository

    queue, _ = drive_queue
    connection = queue.storage.connection
    previous = connection.tokens.read()

    def fail(*args):
        raise RuntimeError("sensitive")

    monkeypatch.setattr(StorageAccountRepository, "bind", fail)
    connection.start()
    with pytest.raises(StorageError) as error:
        connection.callback(next(iter(connection.states)), "code", None)
    assert error.value.code == "OAUTH_FAILED"
    assert connection.tokens.read() == previous


def test_credential_atomic_failure_preserves_previous_and_cleans_temp(tmp_path, monkeypatch):
    import os

    file = CredentialFile(tmp_path / "private")
    file.write({"token": "old-fake"})

    def fail(*args):
        raise OSError("private-path")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(StorageError):
        file.write({"token": "new-fake"})
    assert file.read() == {"token": "old-fake"}
    assert list(file.root.iterdir()) == [file.path]


def test_lost_upload_response_compensates_known_generated_id(drive_queue):
    queue, drive = drive_queue

    def lost_response():
        raise OSError("remote response contains a private value")

    drive.after_upload = lost_response
    assert run(queue).status == S.FAILED
    assert not media(drive)
    assert drive.calls.count("generate-id") == 1
    assert "delete" in drive.calls
    assert not only_video(queue).has_download_history


def test_account_lease_protects_completion_from_disconnect(drive_queue):
    queue, _ = drive_queue
    connection = queue.storage.connection
    started = Event()

    def disconnect():
        started.set()
        connection.disconnect()

    with ThreadPoolExecutor() as executor:
        with connection.lease():
            future = executor.submit(disconnect)
            assert started.wait(1)
            assert not future.done()
            assert connection.status().connected
        future.result(timeout=1)
    assert not connection.status().connected


def test_callback_access_log_omits_code_and_state():
    import logging

    from app.core.logging import OAuthAccessFilter

    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        1,
        "%s %s %s %s %s",
        (
            "127.0.0.1",
            "GET",
            "/api/v1/storage/google-drive/callback?code=private-code&state=private-state",
            "1.1",
            303,
        ),
        None,
    )
    assert OAuthAccessFilter().filter(record)
    assert "private" not in record.getMessage()


def test_credential_reparse_point_rejected_without_read(tmp_path, monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace

    file = CredentialFile(tmp_path / "private")
    original = Path.lstat

    def lstat(path):
        if path == file.root:
            return SimpleNamespace(st_mode=0, st_file_attributes=0x400)
        return original(path)

    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(StorageError) as error:
        file.read()
    assert error.value.code == "STORAGE_CREDENTIAL_FAILED"
