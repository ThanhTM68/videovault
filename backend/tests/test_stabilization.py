from threading import Event, Thread

import pytest
from sqlalchemy import event

from app.repositories.jobs import JobRepository
from app.repositories.storage import StorageAccountRepository
from app.services.queue.models import DownloadPayload
from tests.downloader_fixtures import URL
from tests.test_library import library_queue as shared_library_queue
from tests.test_library import only_video, run
from tests.test_queue import queue as shared_queue

library_queue = shared_library_queue
queue = shared_queue


@pytest.mark.parametrize("kind", ["tags", "collections"])
@pytest.mark.parametrize("remove", [False, True])
def test_organization_mutation_survives_concurrent_queue_writer(library_queue, kind, remove):
    """A worker claim between lookup and membership write must not produce HTTP 500."""
    queue, _ = library_queue
    run(queue)
    video = only_video(queue)
    item = queue.library.organization(kind, "Stabilization")
    if remove:
        queue.library.attach(kind, item.id, video.id)
    queue.submit([DownloadPayload(url=URL + "-next", max_height=1080)])
    attempted = Event()
    reserved = Event()
    release = Event()
    writer_errors = []
    triggered = False
    writes = set()
    worker = None
    engine = queue.sessions.kw["bind"]

    def writer():
        try:
            with queue.sessions.begin() as session:
                attempted.set()
                assert JobRepository(session).claim(queue.clock()) is not None
                reserved.set()
                assert release.wait(3)
        except BaseException as exc:
            writer_errors.append(exc)

    def competing_claim(connection, cursor, statement, parameters, context, executemany):
        nonlocal triggered, worker
        transaction = connection.get_transaction()
        if statement.startswith(("UPDATE ", "INSERT ", "DELETE ")):
            writes.add(transaction)
        if not triggered and statement.startswith("SELECT videos."):
            triggered = True
            worker = Thread(target=writer)
            worker.start()
            assert attempted.wait(3)
            if transaction not in writes:
                assert reserved.wait(3)
            # The writer's commit now waits for this read transaction. An unfenced
            # read-to-write upgrade cannot wait safely and fails SQLITE_BUSY.
            release.set()

    event.listen(engine, "after_cursor_execute", competing_claim)
    try:
        detail = queue.library.attach(kind, item.id, video.id, remove=remove)
        membership = detail.tags if kind == "tags" else detail.collections
        assert any(value.id == item.id for value in membership) is not remove
    finally:
        event.remove(engine, "after_cursor_execute", competing_claim)
        release.set()
        if worker:
            worker.join(4)
            assert not worker.is_alive()
    assert triggered and not writer_errors


@pytest.mark.parametrize("operation", ["bind-new", "bind-existing", "root"])
def test_drive_account_mutation_survives_concurrent_queue_writer(queue, operation):
    if operation != "bind-new":
        with queue.sessions.begin() as session:
            StorageAccountRepository(session).bind("stabilization-account", "Original")
    queue.submit([DownloadPayload(url=URL, max_height=1080)])
    attempted = Event()
    reserved = Event()
    release = Event()
    writer_errors = []
    triggered = False
    writes = set()
    worker = None
    engine = queue.sessions.kw["bind"]

    def writer():
        try:
            with queue.sessions.begin() as session:
                attempted.set()
                assert JobRepository(session).claim(queue.clock()) is not None
                reserved.set()
                assert release.wait(3)
        except BaseException as exc:
            writer_errors.append(exc)

    def competing_claim(connection, cursor, statement, parameters, context, executemany):
        nonlocal triggered, worker
        transaction = connection.get_transaction()
        if statement.startswith(("UPDATE ", "INSERT ", "DELETE ")):
            writes.add(transaction)
        if not triggered and statement.startswith("SELECT storage_accounts."):
            triggered = True
            worker = Thread(target=writer)
            worker.start()
            assert attempted.wait(3)
            if transaction not in writes:
                assert reserved.wait(3)
            release.set()

    event.listen(engine, "after_cursor_execute", competing_claim)
    try:
        with queue.sessions.begin() as session:
            repository = StorageAccountRepository(session)
            if operation == "root":
                repository.root("stabilization-root")
            else:
                repository.bind("stabilization-account", "Updated")
    finally:
        event.remove(engine, "after_cursor_execute", competing_claim)
        release.set()
        if worker:
            worker.join(4)
            assert not worker.is_alive()
    assert triggered and not writer_errors
    with queue.sessions() as session:
        row = StorageAccountRepository(session).get_drive()
        assert row.provider_account_id == "stabilization-account"
        if operation == "root":
            assert row.config_json["root_folder_id"] == "stabilization-root"
        else:
            assert row.display_name == "Updated"
