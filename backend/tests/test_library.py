import hashlib
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Thread

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application import create_app
from app.core.config import Settings
from app.db.session import create_session_factory
from app.models import Creator, Download, MediaFile, Video
from app.models.enums import DownloadStatus as D
from app.models.enums import JobStatus as S
from app.models.enums import Platform
from app.repositories.library import LibraryRepository
from app.services.downloader.service import DownloaderService
from app.services.library.errors import LibraryFileError
from app.services.library.files import CHUNK_SIZE, LocalFiles
from app.services.library.locks import identity_lock
from app.services.queue.models import DownloadPayload
from app.services.queue.recovery import recover_stale_jobs
from app.services.queue.service import QueueService
from app.workers.download_worker import execute_download
from tests.downloader_fixtures import URL
from tests.test_queue import ControlledAdapter


@pytest.fixture
def library_queue(db_engine: Engine, settings: Settings, local_media: Path):
    adapter = ControlledAdapter(local_media)
    adapter.release.set()
    queue = QueueService(
        create_session_factory(db_engine), DownloaderService(settings, {Platform.YOUTUBE: adapter})
    )
    return queue, adapter


def run(queue: QueueService, url: str = URL, *, force: bool = False):
    created = queue.submit([DownloadPayload(url=url, max_height=1080, force=force)])[0]
    claim = queue.claim()
    assert claim.id == created.id
    execute_download(queue, claim, Event())
    return queue.get(created.id)


def only_video(queue: QueueService):
    return queue.library.list(page=1, page_size=25).items[0]


def keys(queue: QueueService):
    with queue.sessions() as session:
        return list(session.scalars(select(MediaFile.storage_key)))


def test_normal_duplicate_and_identity_url_variant(library_queue):
    queue, adapter = library_queue
    assert run(queue).status == S.COMPLETED
    video = only_video(queue)
    assert video.has_file and video.has_download_history
    assert run(queue, URL + "&tracking=value").status == S.SKIPPED_DUPLICATE
    assert adapter.started == 1
    assert queue.library.list(page=1, page_size=25).total == 1
    assert queue.library.history(page=1, page_size=25).total == 1
    assert len(keys(queue)) == 1
    assert not list(queue.downloader.settings.temp_storage_root.iterdir())


def test_remove_history_keeps_file_then_normal_download(library_queue):
    queue, adapter = library_queue
    run(queue)
    video = only_video(queue)
    original = keys(queue)[0]
    detail = queue.library.destroy(video.id, "history")
    assert detail.has_file and not detail.has_download_history
    assert queue.library.files.exists(original)
    with queue.sessions() as session:
        assert session.scalar(select(MediaFile)).download_id is None
    assert run(queue).status == S.COMPLETED and adapter.started == 2
    assert len(keys(queue)) == 2


def test_force_creates_separate_event_and_file(library_queue):
    queue, adapter = library_queue
    run(queue)
    assert run(queue, force=True).status == S.COMPLETED
    events = queue.library.history(page=1, page_size=25).items
    assert len(events) == 2 and events[0].forced and not events[1].forced
    assert events[0].id != events[1].id
    assert len(set(keys(queue))) == 2 and adapter.started == 2
    assert all(queue.library.files.exists(key) for key in keys(queue))


def test_delete_file_keeps_history_skip_then_force(library_queue):
    queue, adapter = library_queue
    run(queue)
    video = only_video(queue)
    detail = queue.library.destroy(video.id, "file")
    assert not detail.has_file and detail.has_download_history
    assert detail.files[0].state == "deleted"
    assert not queue.library.files.exists(keys(queue)[0])
    assert run(queue).status == S.SKIPPED_DUPLICATE and adapter.started == 1
    assert run(queue, force=True).status == S.COMPLETED and adapter.started == 2
    queue.library.destroy(video.id, "file")
    assert queue.library.destroy(video.id, "file").has_download_history


def test_delete_all_preserves_metadata_and_organization(library_queue):
    queue, adapter = library_queue
    run(queue)
    video = only_video(queue)
    tag = queue.library.organization("tags", " Personal ")
    collection = queue.library.organization("collections", "Research")
    queue.library.attach("tags", tag.id, video.id)
    queue.library.attach("collections", collection.id, video.id)
    detail = queue.library.destroy(video.id, "all")
    assert not detail.has_file and not detail.has_download_history
    assert (
        detail.title == video.title
        and detail.tags[0].id == tag.id
        and detail.collections[0].id == collection.id
    )
    assert run(queue).status == S.COMPLETED and adapter.started == 2


def test_hash_persisted_and_equal_bytes_do_not_merge_identities(library_queue, local_media):
    queue, _ = library_queue
    run(queue)
    run(queue, URL + "-other")
    expected = hashlib.sha256(local_media.read_bytes()).hexdigest()
    with queue.sessions() as session:
        files = list(session.scalars(select(MediaFile)))
        assert len(files) == 2 and all(file.sha256 == expected for file in files)
        assert files[0].video_id != files[1].video_id


def test_missing_file_reconciliation_and_history_retained(library_queue):
    queue, _ = library_queue
    run(queue)
    video = only_video(queue)
    queue.library.files.path(keys(queue)[0]).unlink()
    detail = queue.library.detail(video.id)
    assert (
        not detail.has_file and detail.has_download_history and detail.files[0].state == "missing"
    )
    assert queue.library.list(page=1, page_size=25, has_file=False).total == 1
    assert queue.library.destroy(video.id, "file").files[0].state == "deleted"


def test_concurrent_same_video_one_transfer(library_queue):
    queue, adapter = library_queue
    queue.submit([DownloadPayload(url=URL, max_height=1080)] * 2)
    claims = [queue.claim(), queue.claim()]
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda claim: execute_download(queue, claim, Event()), claims))
    assert {queue.get(claim.id).status for claim in claims} == {S.COMPLETED, S.SKIPPED_DUPLICATE}
    assert adapter.started == 1
    assert len(keys(queue)) == 1 and queue.library.history(page=1, page_size=25).total == 1


def test_delete_all_serializes_with_active_download(library_queue):
    queue, adapter = library_queue
    adapter.release.clear()
    queue.submit([DownloadPayload(url=URL, max_height=1080)])
    claim = queue.claim()
    entered = Event()

    def destroy(video_id):
        entered.set()
        return queue.library.destroy(video_id, "all")

    with ThreadPoolExecutor(2) as pool:
        worker = pool.submit(execute_download, queue, claim, Event())
        try:
            adapter.wait_started(1)
            deletion = pool.submit(destroy, only_video(queue).id)
            assert entered.wait(2) and not deletion.done()
        finally:
            adapter.release.set()
        worker.result(timeout=5)
        result = deletion.result(timeout=5)
    assert queue.get(claim.id).status == S.COMPLETED
    assert not result.has_file and not result.has_download_history
    assert result.files[0].state == "deleted"
    assert not list(queue.library.files.root.iterdir())


def test_database_rejects_duplicate_execution_event(library_queue):
    queue, _ = library_queue
    run(queue)
    with queue.sessions() as session:
        original = session.scalar(select(Download))
        values = {
            "video_id": original.video_id,
            "job_id": original.job_id,
            "attempt_number": original.attempt_number,
        }
    with pytest.raises(IntegrityError), queue.sessions.begin() as session:
        session.add(Download(**values))
    assert queue.library.history(page=1, page_size=25).total == 1


@pytest.mark.parametrize("failure", ["copy", "hash", "persist"])
def test_finalization_failures_never_complete_and_cleanup(library_queue, monkeypatch, failure):
    queue, _ = library_queue

    def fail(*args, **kwargs):
        raise OSError("secret-local-path")

    if failure == "copy":
        monkeypatch.setattr(queue.library.files, "finalize", fail)
    elif failure == "hash":
        monkeypatch.setattr(queue.library.files, "hash_file", fail)
    else:
        monkeypatch.setattr(LibraryRepository, "save_result", fail)
    result = run(queue)
    assert result.status == S.FAILED and "secret" not in result.model_dump_json()
    assert keys(queue) == []
    root = queue.downloader.settings.local_storage_root
    assert not root.exists() or not list(root.iterdir())
    assert not list(queue.downloader.settings.temp_storage_root.iterdir())
    event = queue.library.history(page=1, page_size=25).items[0]
    assert event.status == D.FAILED and not only_video(queue).has_download_history


def test_cancel_at_durable_commit_cleans_both_roots(library_queue, monkeypatch):
    queue, _ = library_queue
    finish = queue.finish

    def cancel_before_commit(claim, **kwargs):
        if kwargs.get("on_completed"):
            queue.cancel(claim.id)
        return finish(claim, **kwargs)

    monkeypatch.setattr(queue, "finish", cancel_before_commit)
    assert run(queue).status == S.CANCELLED
    assert keys(queue) == []
    assert not list(queue.downloader.settings.local_storage_root.iterdir())
    assert queue.library.history(page=1, page_size=25).items[0].status == D.CANCELLED


def test_retry_has_one_history_event_per_execution_attempt(library_queue):
    queue, adapter = library_queue
    result = run(queue, URL + "-bad")
    assert result.status == S.FAILED
    queue.retry(result.id)
    claim = queue.claim()
    execute_download(queue, claim, Event())
    events = queue.library.history(page=1, page_size=25).items
    assert len(events) == 2 and {event.attempt_number for event in events} == {1, 2}
    assert adapter.started == 2 and all(event.status == D.FAILED for event in events)


def test_recovery_closes_unfinished_attempt(library_queue):
    queue, _ = library_queue
    queue.submit([DownloadPayload(url=URL, max_height=1080)])
    claim = queue.claim()
    metadata = queue.downloader.resolve(URL)
    queue.library.begin_attempt(metadata, DownloadPayload(url=URL, max_height=1080), claim)
    queue.clock = lambda: datetime.now(UTC) + timedelta(minutes=2)
    assert recover_stale_jobs(queue) == 1
    event = queue.library.history(page=1, page_size=25).items[0]
    assert event.status == D.FAILED and event.failure_code == "WORKER_LOST"


@pytest.mark.parametrize(
    "key",
    [
        "../../outside.txt",
        "..\\..\\outside.txt",
        "C:\\Windows\\outside.txt",
        "/etc/passwd",
        "D:/personal/video.mp4",
    ],
)
def test_delete_refuses_external_keys(tmp_path, key):
    outside = tmp_path / "outside.txt"
    outside.write_text("keep")
    files = LocalFiles(tmp_path / "managed", tmp_path / "temp")
    with pytest.raises(LibraryFileError, match="outside"):
        files.delete(key)
    assert outside.read_text() == "keep"


def test_symlink_delete_refused(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("keep")
    root = tmp_path / "managed"
    root.mkdir()
    try:
        (root / "link.txt").symlink_to(outside)
    except OSError:
        pytest.skip("Windows symlink creation needs developer mode or privilege")
    with pytest.raises(LibraryFileError):
        LocalFiles(root, tmp_path / "temp").delete("link.txt")
    assert outside.exists()


def test_hash_streams_chunks_and_safe_failure(tmp_path, monkeypatch):
    root = tmp_path / "managed"
    root.mkdir()
    files = LocalFiles(root, tmp_path / "temp")
    content = b"a" * (CHUNK_SIZE * 2 + 7)
    (root / "fixture.bin").write_bytes(content)
    sizes = []
    original = Path.open

    class RecordingReader:
        def __enter__(self):
            self.stream = original(root / "fixture.bin", "rb")
            return self

        def read(self, size):
            sizes.append(size)
            return self.stream.read(size)

        def __exit__(self, *args):
            self.stream.close()

    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: RecordingReader())
    assert files.hash_file("fixture.bin") == hashlib.sha256(content).hexdigest()
    assert sizes == [CHUNK_SIZE] * 4
    monkeypatch.setattr(Path, "open", original)
    with pytest.raises(LibraryFileError):
        files.hash_file("missing.bin")

    def unreadable(*args, **kwargs):
        raise PermissionError("secret")

    monkeypatch.setattr(Path, "open", unreadable)
    with pytest.raises(LibraryFileError) as error:
        files.hash_file("fixture.bin")
    assert "secret" not in str(error.value)


def test_metadata_merge_and_creator_identity(library_queue):
    queue, _ = library_queue
    source = queue.downloader.resolve(URL).model_copy(
        update={"creator_id": "known", "creator": "Researcher"}
    )
    with queue.sessions.begin() as session:
        row = LibraryRepository(session).upsert(source)
        video_id = row.id
    with queue.sessions.begin() as session:
        row = LibraryRepository(session).upsert(
            source.model_copy(update={"title": None, "description": None, "creator": None})
        )
        assert row.id == video_id and row.title == source.title and row.creator.name == "Researcher"
    with queue.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Creator)) == 1


def test_api_search_filters_organization_actions_and_privacy(library_queue, settings):
    queue, _ = library_queue
    run(queue)
    app = create_app(settings, downloader=queue.downloader, start_workers=False)
    with TestClient(app) as client:
        video = client.get("/api/v1/videos").json()["items"][0]
        video_id = video["id"]
        tag = client.post("/api/v1/tags", json={"name": "  Research  "}).json()
        assert tag["name"] == "research"
        assert client.post("/api/v1/tags", json={"name": "RESEARCH"}).json() == tag
        collection = client.post("/api/v1/collections", json={"name": "Saved"}).json()
        for kind, item in [("tags", tag), ("collections", collection)]:
            path = (
                f"/api/v1/videos/{video_id}/tags/{item['id']}"
                if kind == "tags"
                else f"/api/v1/collections/{item['id']}/videos/{video_id}"
            )
            assert client.post(path).status_code == 200
            assert len(client.post(path).json()[kind]) == 1
            assert len(client.get("/api/v1/" + kind).json()) == 1
        for params in [
            {"search": "Local research"},
            {"search": "Fixture creator"},
            {"platform": "youtube"},
            {"has_file": "true"},
            {"has_download_history": "true"},
            {"tag_id": tag["id"]},
            {"collection_id": collection["id"]},
        ]:
            # Creator name depends on fixture; explicit metadata merge tested separately.
            if params.get("search") == "Fixture creator":
                params["search"] = video["creator"] or "Local research"
            assert client.get("/api/v1/videos", params=params).json()["total"] == 1
        assert client.get("/api/v1/videos", params={"search": "%secret_%"}).json()["total"] == 0
        assert client.get("/api/v1/videos?page_size=1&page=2").json()["items"] == []
        assert client.get("/api/v1/videos?page_size=101").status_code == 422
        detail = client.get(f"/api/v1/videos/{video_id}").json()
        assert "storage_key" not in str(detail)
        assert all(item["storage_provider"] == "local" for item in detail["files"])
        assert all("/" not in item["file_name"] for item in detail["files"])
        assert str(settings.local_storage_root) not in str(detail)
        assert client.get("/api/v1/history?status=completed&platform=youtube").json()["total"] == 1
        assert client.post(f"/api/v1/videos/{video_id}/redownload").status_code == 202
        assert client.post(f"/api/v1/videos/{video_id}/tags/missing").status_code == 404
        assert client.get("/api/v1/videos/missing").status_code == 404
        assert client.delete(f"/api/v1/videos/{video_id}/tags/{tag['id']}").json()["tags"] == []
        assert (
            client.delete(f"/api/v1/collections/{collection['id']}/videos/{video_id}").json()[
                "collections"
            ]
            == []
        )
        assert client.delete(f"/api/v1/videos/{video_id}/file").json()["has_download_history"]
        assert not client.delete(f"/api/v1/videos/{video_id}/history").json()[
            "has_download_history"
        ]
        assert client.delete(f"/api/v1/videos/{video_id}/all").status_code == 200


def test_library_migration_0002_data_preservation(db_engine: Engine, alembic_config: Config):
    with db_engine.begin() as connection:
        alembic_config.attributes["connection"] = connection
        command.downgrade(alembic_config, "0002_queue")
        connection.exec_driver_sql(
            "INSERT INTO videos(id,platform,platform_video_id,canonical_url,title,description,"
            "metadata_json,discovered_at) VALUES ('v','youtube','source',"
            "'https://youtu.be/source','keep','','{}','2026-10-03')"
        )
        connection.exec_driver_sql(
            "INSERT INTO downloads(id,video_id,requested_quality,status,forced,created_at) "
            "VALUES ('d','v','best','completed',0,'2026-10-03')"
        )
        connection.exec_driver_sql(
            "INSERT INTO media_files(id,video_id,download_id,storage_provider,storage_key,"
            "file_name,mime_type,size_bytes,kind,created_at) VALUES "
            "('m','v','d','local','test.mp4','test.mp4','video/mp4',10,'original','2026-10-03')"
        )
    for target in ["head", "0002_queue", "head"]:
        with db_engine.begin() as connection:
            alembic_config.attributes["connection"] = connection
            (command.downgrade if target == "0002_queue" else command.upgrade)(
                alembic_config, target
            )
            assert (
                connection.exec_driver_sql("SELECT title FROM videos WHERE id='v'").scalar_one()
                == "keep"
            )
            assert (
                connection.exec_driver_sql(
                    "SELECT download_id FROM media_files WHERE id='m'"
                ).scalar_one()
                == "d"
            )
            assert (
                connection.exec_driver_sql("SELECT status FROM downloads WHERE id='d'").scalar_one()
                == "completed"
            )
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    alembic_config.attributes.pop("connection", None)


def test_db_commit_failure_rolls_back_job_event_and_media(library_queue):
    queue, _ = library_queue
    failed_once = False

    def fail_commit(session: Session) -> None:
        nonlocal failed_once
        if not failed_once and session.scalar(
            select(Download.id).where(Download.status == D.COMPLETED)
        ):
            failed_once = True
            raise RuntimeError("secret commit diagnostics")

    event.listen(Session, "before_commit", fail_commit)
    try:
        result = run(queue)
    finally:
        event.remove(Session, "before_commit", fail_commit)
    assert failed_once and result.status == S.FAILED
    assert keys(queue) == [] and not list(queue.downloader.settings.local_storage_root.iterdir())
    assert queue.library.history(page=1, page_size=25).items[0].status == D.FAILED


def test_corrupt_database_path_cannot_delete_external_file(library_queue, tmp_path):
    queue, _ = library_queue
    run(queue)
    video = only_video(queue)
    external = tmp_path / "personal.txt"
    external.write_text("keep")
    with queue.sessions.begin() as session:
        session.scalar(select(MediaFile)).storage_key = external.as_posix()
    with pytest.raises(LibraryFileError):
        queue.library.destroy(video.id, "all")
    assert external.read_text() == "keep"
    with queue.sessions() as session:
        assert session.scalar(select(Download)).status == D.COMPLETED
        assert session.scalar(select(MediaFile)).deleted_at is None


def test_delete_failure_does_not_remove_history(library_queue, monkeypatch):
    queue, _ = library_queue
    run(queue)

    def fail(key):
        raise LibraryFileError("FILE_DELETE_FAILED")

    monkeypatch.setattr(queue.library.files, "delete", fail)
    with pytest.raises(LibraryFileError):
        queue.library.destroy(only_video(queue).id, "all")
    assert only_video(queue).has_download_history and only_video(queue).has_file


def test_windows_junction_cannot_escape_managed_root(tmp_path):
    if os.name != "nt":
        pytest.skip("Windows junction-specific test")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "personal.txt").write_text("keep")
    root = tmp_path / "managed"
    root.mkdir()
    junction = root / "junction"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)], capture_output=True, timeout=10
    )
    assert result.returncode == 0
    try:
        with pytest.raises(LibraryFileError):
            LocalFiles(root, tmp_path / "temp").delete("junction/personal.txt")
        assert (outside / "personal.txt").read_text() == "keep"
    finally:
        # Remove the junction itself, never the target directory contents.
        junction.rmdir()


def test_media_io_has_no_open_database_session(library_queue, monkeypatch):
    queue, adapter = library_queue
    original_download = adapter.download
    original_hash = queue.library.files.hash_file

    def download(*args, **kwargs):
        assert queue.sessions.kw["bind"].pool.checkedout() == 0
        return original_download(*args, **kwargs)

    def hash_file(*args, **kwargs):
        assert queue.sessions.kw["bind"].pool.checkedout() == 0
        return original_hash(*args, **kwargs)

    monkeypatch.setattr(adapter, "download", download)
    monkeypatch.setattr(queue.library.files, "hash_file", hash_file)
    assert run(queue).status == S.COMPLETED


def test_preview_reports_db_state_and_source_redownload_refuses_invalid_url(
    library_queue, settings
):
    queue, _ = library_queue
    run(queue)
    video = only_video(queue)
    app = create_app(settings, downloader=queue.downloader, start_workers=False)
    with TestClient(app) as client:
        preview = client.post("/api/v1/videos/resolve", json={"url": URL}).json()
        assert (
            preview["video_id"] == video.id
            and preview["has_file"]
            and preview["has_download_history"]
        )
        client.delete(f"/api/v1/videos/{video.id}/file")
        preview = client.post("/api/v1/videos/resolve", json={"url": URL}).json()
        assert not preview["has_file"] and preview["has_download_history"]
        with queue.sessions.begin() as session:
            session.get(Video, video.id).canonical_url = "file:///private"
        response = client.post(f"/api/v1/videos/{video.id}/redownload")
        assert response.status_code == 409 and response.json()["error"]["code"] == "CONFLICT"


def test_cancel_while_waiting_for_identity_lock_starts_no_transfer(library_queue):
    queue, adapter = library_queue
    submitted = queue.submit([DownloadPayload(url=URL, max_height=1080)])[0]
    claim = queue.claim()
    cancellation = Event()
    resolved = adapter.resolve(URL)
    with identity_lock(resolved.platform.value, resolved.platform_video_id):
        worker = Thread(target=execute_download, args=(queue, claim, cancellation))
        worker.start()
        queue.cancel(submitted.id)
        cancellation.set()
        worker.join(timeout=2)
        assert not worker.is_alive()
    assert queue.get(submitted.id).status == S.CANCELLED
    assert adapter.started == 0
    assert queue.library.history(page=1, page_size=25).total == 0


def test_cancellation_after_validated_return_is_acknowledged_after_cleanup(
    library_queue, monkeypatch
):
    queue, adapter = library_queue
    cancellation = Event()
    original_download = queue.downloader.download
    original_discard = queue.downloader.discard_result
    queue.submit([DownloadPayload(url=URL, max_height=1080)])
    claim = queue.claim()

    def cancel_after_return(*args, **kwargs):
        result = original_download(*args, **kwargs)
        cancellation.set()
        return result

    def inspect_discard(result):
        assert queue.get(claim.id).status == S.PROCESSING
        original_discard(result)

    monkeypatch.setattr(queue.downloader, "download", cancel_after_return)
    monkeypatch.setattr(queue.downloader, "discard_result", inspect_discard)
    execute_download(queue, claim, cancellation)
    assert queue.get(claim.id).status == S.CANCELLED
    assert not adapter.paths[0].parent.exists()
    assert keys(queue) == []
