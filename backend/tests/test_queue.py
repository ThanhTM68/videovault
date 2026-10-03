import logging
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Condition, Event, Thread

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

from app.application import create_app
from app.core.config import Settings
from app.core.errors import ConflictError
from app.db.session import create_session_factory
from app.models import Job, MediaFile
from app.models.enums import JobStatus as S
from app.models.enums import Platform
from app.repositories.jobs import JobRepository
from app.services.downloader.base import AdapterCapabilities, ProgressCallback
from app.services.downloader.cancellation import check_cancelled
from app.services.downloader.errors import AuthenticationRequiredError, UnsupportedPlatformError
from app.services.downloader.metadata import normalize_metadata
from app.services.downloader.models import (
    DownloadRequest,
    NormalizedVideo,
    ProgressEvent,
    VideoFormat,
)
from app.services.downloader.models import ProgressPhase as P
from app.services.downloader.service import DownloaderService
from app.services.media import probe
from app.services.queue.models import DownloadPayload
from app.services.queue.recovery import recover_stale_jobs
from app.services.queue.service import QueueService
from app.services.queue.state_machine import validate_transition
from app.workers.download_worker import ProgressBridge, execute_download
from app.workers.manager import WorkerManager
from tests.downloader_fixtures import FIXTURES, URL


def payload(url: str = URL) -> DownloadPayload:
    return DownloadPayload(url=url, max_height=1080)


@pytest.fixture
def queue(db_engine: Engine, settings: Settings, tmp_path: Path) -> QueueService:
    settings = settings.model_copy(update={"temp_storage_root": tmp_path / "temp"})
    return QueueService(create_session_factory(db_engine), DownloaderService(settings))


def running(queue: QueueService):
    queue.submit([payload()])
    claim = queue.claim()
    assert claim is not None
    queue.progress(claim, S.DOWNLOADING, "downloading", 20)
    return claim


def wait_status(queue: QueueService, job_id: str, status: S):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        view = queue.get(job_id)
        if view.status == status:
            return view
        Event().wait(0.01)
    pytest.fail(f"Job did not reach {status}: {queue.get(job_id).status}")


class ControlledAdapter:
    capabilities = AdapterCapabilities()

    def __init__(self, media: Path) -> None:
        self.media = media
        self.release = Event()
        self.condition = Condition()
        self.active = 0
        self.maximum = 0
        self.started = 0
        self.paths: list[Path] = []

    def resolve(self, url: str) -> NormalizedVideo:
        info = FIXTURES["combined"] | {"id": url.rsplit("=", 1)[-1], "webpage_url": url}
        return normalize_metadata(info, Platform.YOUTUBE, url)

    def get_formats(self, video: NormalizedVideo) -> tuple[VideoFormat, ...]:
        return video.formats

    def download(
        self,
        video: NormalizedVideo,
        request: DownloadRequest,
        output_stem: Path,
        progress: ProgressCallback,
    ) -> Path:
        partial = output_stem.with_suffix(".part")
        partial.write_bytes(b"partial")
        with self.condition:
            self.paths.append(partial)
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            self.started += 1
            self.condition.notify_all()
        try:
            assert self.release.wait(5), "Test downloader was not released"
            check_cancelled()
            if video.platform_video_id.endswith("bad"):
                raise RuntimeError("secret-token-should-never-be-logged")
            progress(ProgressEvent(phase=P.DOWNLOADING, percent=100))
            progress(ProgressEvent(phase=P.PROCESSING))
            partial.unlink()
            output = output_stem.with_suffix(".mp4")
            shutil.copyfile(self.media, output)
            return output
        finally:
            with self.condition:
                self.active -= 1
                self.condition.notify_all()

    def wait_started(self, count: int) -> None:
        with self.condition:
            assert self.condition.wait_for(lambda: self.started >= count, timeout=5)


def controlled(queue: QueueService, settings: Settings, media: Path, tmp_path: Path):
    settings = settings.model_copy(update={"temp_storage_root": tmp_path / "temp"})
    adapter = ControlledAdapter(media)
    queue.downloader = DownloaderService(settings, {Platform.YOUTUBE: adapter})
    return adapter


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (S.QUEUED, S.RESOLVING),
        (S.QUEUED, S.CANCELLED),
        (S.RESOLVING, S.DOWNLOADING),
        (S.DOWNLOADING, S.PROCESSING),
        (S.PROCESSING, S.COMPLETED),
        (S.PROCESSING, S.UPLOADING),
        (S.UPLOADING, S.COMPLETED),
        (S.DOWNLOADING, S.FAILED),
        (S.PROCESSING, S.CANCELLED),
    ],
)
def test_allowed_transitions(source: S, target: S) -> None:
    validate_transition(source, target)


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (S.COMPLETED, S.DOWNLOADING),
        (S.CANCELLED, S.RESOLVING),
        (S.FAILED, S.COMPLETED),
        (S.QUEUED, S.COMPLETED),
        (S.RESOLVING, S.PROCESSING),
        (S.DOWNLOADING, S.UPLOADING),
        (S.QUEUED, S.SKIPPED_DUPLICATE),
        (S.FAILED, S.QUEUED),
    ],
)
def test_invalid_transitions(source: S, target: S) -> None:
    with pytest.raises(ConflictError):
        validate_transition(source, target)


def test_submission_is_durable_and_all_or_nothing(
    queue: QueueService, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs = queue.submit([payload(), payload(URL + "-second")])
    other = QueueService(queue.sessions, queue.downloader)
    assert [other.get(job.id).status for job in jobs] == [S.QUEUED, S.QUEUED]
    with pytest.raises(UnsupportedPlatformError):
        queue.submit([payload(), payload("https://example.com/video")])
    assert queue.list().total == 2
    add = JobRepository.add
    calls = 0

    def fail_second(self: JobRepository, job: Job) -> Job:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated write failure")
        return add(self, job)

    monkeypatch.setattr(JobRepository, "add", fail_second)
    with pytest.raises(RuntimeError):
        queue.submit([payload(), payload()])
    assert other.list().total == 2


def test_one_job_many_concurrent_claimers(queue: QueueService) -> None:
    job = queue.submit([payload()])[0]
    barrier = Barrier(8)

    def claim(_):
        barrier.wait(timeout=5)
        return queue.claim()

    with ThreadPoolExecutor(max_workers=8) as workers:
        claims = list(workers.map(claim, range(8)))
    successes = [claim for claim in claims if claim]
    assert len(successes) == 1
    assert successes[0].id == job.id
    assert queue.get(job.id).attempt_count == 1


def test_cancel_queued_and_terminal_conflicts(queue: QueueService) -> None:
    job = queue.submit([payload()])[0]
    cancelled = queue.cancel(job.id)
    assert cancelled.status == S.CANCELLED
    assert cancelled.cancelled_at is not None and cancelled.completed_at is not None
    assert queue.claim() is None
    for operation in (queue.cancel, queue.retry):
        with pytest.raises(ConflictError):
            operation(job.id)


def test_retry_attempt_accounting_and_fencing(queue: QueueService) -> None:
    claim = running(queue)
    for attempt in range(1, 4):
        assert claim.attempt == attempt
        queue.finish(claim, error_code="DOWNLOAD_FAILED", error_message="Download failed")
        failed = queue.get(claim.id)
        assert failed.status == S.FAILED and failed.completed_at is not None
        if attempt < 3:
            queued = queue.retry(claim.id)
            assert queued.attempt_count == attempt and queued.progress_percent == 0
            assert queued.error is None and queued.started_at is None
            previous = claim
            claim = queue.claim()
            assert claim is not None
            assert queue.heartbeat(previous) is None
            assert not queue.finish(previous, cancelled=True)
        else:
            with pytest.raises(ConflictError):
                queue.retry(claim.id)
    assert queue.claim() is None


def test_progress_throttle_and_no_early_completion(
    queue: QueueService, monkeypatch: pytest.MonkeyPatch
) -> None:
    claim = running(queue)
    now = [0.0]
    writes = []
    real = queue.progress

    def record(*args):
        writes.append(args)
        real(*args)

    monkeypatch.setattr(queue, "progress", record)
    bridge = ProgressBridge(queue, claim, clock=lambda: now[0])
    for n in range(1000):
        bridge(ProgressEvent(phase=P.DOWNLOADING, percent=n / 10))
    assert len(writes) == 1
    now[0] = 1
    bridge(ProgressEvent(phase=P.DOWNLOADING, percent=100))
    assert queue.get(claim.id).progress_percent == 99
    bridge(ProgressEvent(phase=P.PROCESSING))
    for _ in range(100):
        bridge(ProgressEvent(phase=P.DOWNLOADING))
        bridge(ProgressEvent(phase=P.PROCESSING))
    assert len(writes) == 3
    now[0] = 6
    bridge(ProgressEvent(phase=P.PROCESSING))
    assert len(writes) == 4
    bridge(ProgressEvent(phase=P.VALIDATING))
    bridge(ProgressEvent(phase=P.COMPLETED, percent=100))
    assert queue.get(claim.id).status == S.PROCESSING
    assert queue.get(claim.id).current_step == "validating"
    assert queue.get(claim.id).progress_percent < 100
    assert queue.finish(claim)
    assert queue.get(claim.id).progress_percent == 100
    with pytest.raises(ConflictError):
        queue.retry(claim.id)
    with pytest.raises(ConflictError):
        queue.cancel(claim.id)


def test_recovery_stale_fresh_terminal_and_exhausted(queue: QueueService) -> None:
    now = datetime(2026, 10, 2, tzinfo=UTC)
    queue.clock = lambda: now
    rows = [
        Job(
            type="download",
            status=status,
            payload_json=payload().model_dump(),
            attempt_count=attempt,
            max_attempts=3,
            created_at=now - timedelta(minutes=5),
            heartbeat_at=heartbeat,
            cancel_requested_at=cancel,
        )
        for status, attempt, heartbeat, cancel in [
            (S.QUEUED, 0, None, None),
            (S.RESOLVING, 1, now - timedelta(minutes=2), None),
            (S.DOWNLOADING, 1, now - timedelta(minutes=2), None),
            (S.PROCESSING, 3, now - timedelta(minutes=2), None),
            (S.UPLOADING, 1, None, None),
            (S.DOWNLOADING, 1, now, None),
            (S.COMPLETED, 1, now - timedelta(minutes=2), None),
            (S.DOWNLOADING, 1, now - timedelta(minutes=2), now),
        ]
    ]
    with queue.sessions.begin() as session:
        session.add_all(rows)
        session.flush()
        ids = [row.id for row in rows]
    assert recover_stale_jobs(queue) == 5
    assert [queue.get(id).status for id in ids] == [
        S.QUEUED,
        S.QUEUED,
        S.QUEUED,
        S.FAILED,
        S.QUEUED,
        S.DOWNLOADING,
        S.COMPLETED,
        S.CANCELLED,
    ]
    assert queue.get(ids[3]).error.code == "WORKER_LOST"
    now += timedelta(seconds=61)
    assert recover_stale_jobs(queue) == 1
    assert queue.get(ids[5]).status == S.QUEUED


@pytest.mark.parametrize("race", ["heartbeat", "cancel"])
def test_recovery_rechecks_races(
    queue: QueueService, monkeypatch: pytest.MonkeyPatch, race: str
) -> None:
    now = datetime.now(UTC)
    queue.clock = lambda: now - timedelta(minutes=2)
    claim = running(queue)
    queue.clock = lambda: now
    write = queue._write
    happened = False

    def racing_write(view, values, **kwargs):
        nonlocal happened
        if kwargs.get("operation") == "recover" and not happened:
            happened = True
            if race == "heartbeat":
                queue.heartbeat(claim)
            else:
                queue.cancel(claim.id)
        return write(view, values, **kwargs)

    monkeypatch.setattr(queue, "_write", racing_write)
    assert recover_stale_jobs(queue) == 0
    assert queue.get(claim.id).status == S.DOWNLOADING
    if race == "cancel":
        assert recover_stale_jobs(queue) == 1
        assert queue.get(claim.id).status == S.CANCELLED


def test_worker_limit_pause_resume_and_independent_heartbeat(
    queue: QueueService, settings: Settings, local_media: Path, tmp_path: Path
) -> None:
    adapter = controlled(queue, settings, local_media, tmp_path)
    now = [datetime.now(UTC)]
    queue.clock = lambda: now[0]
    jobs = queue.submit([payload(URL + f"-{i}") for i in range(5)])
    manager = WorkerManager(queue, 2, poll_seconds=0.01)
    manager.start()
    try:
        adapter.wait_started(2)
        manager.pause()
        assert adapter.started == 2 and adapter.maximum == 2
        assert queue.list(status=S.QUEUED).total == 3
        now[0] += timedelta(seconds=30)
        manager.tick()
        active = queue.list(status=S.DOWNLOADING).items
        assert len(active) == 2 and all(job.heartbeat_at == now[0] for job in active)
        adapter.release.set()
        for job in active:
            wait_status(queue, job.id, S.COMPLETED)
        assert adapter.started == 2
        manager.resume()
        for job in jobs:
            wait_status(queue, job.id, S.COMPLETED)
        assert adapter.maximum == 2 and adapter.started == 5
    finally:
        adapter.release.set()
        assert manager.stop()
    assert all(not thread.is_alive() for thread in manager.threads)
    assert queue.sessions.kw["bind"].pool.checkedout() == 0


def test_active_cancel_waits_for_stop_and_cleans_partial(
    queue: QueueService, settings: Settings, local_media: Path, tmp_path: Path
) -> None:
    adapter = controlled(queue, settings, local_media, tmp_path)
    job = queue.submit([payload()])[0]
    manager = WorkerManager(queue, 1, poll_seconds=0.01)
    manager.start()
    try:
        adapter.wait_started(1)
        requested = manager.cancel(job.id)
        assert requested.status == S.DOWNLOADING and requested.cancel_requested_at is not None
        assert requested.cancelled_at is None
        assert adapter.paths[0].exists()
        adapter.release.set()
        cancelled = wait_status(queue, job.id, S.CANCELLED)
        assert cancelled.cancelled_at is not None and cancelled.progress_percent < 100
        assert not adapter.paths[0].parent.exists()
    finally:
        adapter.release.set()
        assert manager.stop()


def test_cancel_racing_validated_return_discards_before_ack(
    queue: QueueService,
    settings: Settings,
    local_media: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = controlled(queue, settings, local_media, tmp_path)
    adapter.release.set()
    claim = running(queue)
    finish = queue.finish

    def race(claim, **kwargs):
        if kwargs.get("on_completed"):
            queue.cancel(claim.id)
        return finish(claim, **kwargs)

    monkeypatch.setattr(queue, "finish", race)
    discard = queue.downloader.discard_result

    def inspect_discard(result):
        assert queue.get(claim.id).status == S.PROCESSING
        discard(result)

    monkeypatch.setattr(queue.downloader, "discard_result", inspect_discard)
    execute_download(queue, claim, Event())
    assert queue.get(claim.id).status == S.CANCELLED
    assert not adapter.paths[0].parent.exists()


def test_failure_isolation_and_sanitized_error(
    queue: QueueService,
    settings: Settings,
    local_media: Path,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    adapter = controlled(queue, settings, local_media, tmp_path)
    adapter.release.set()
    jobs = queue.submit([payload(URL + "-bad"), payload(URL + "-good")])
    manager = WorkerManager(queue, 1, poll_seconds=0.01)
    with caplog.at_level(logging.ERROR):
        manager.start()
        try:
            failed = wait_status(queue, jobs[0].id, S.FAILED)
            wait_status(queue, jobs[1].id, S.COMPLETED)
            assert failed.error.code == "INTERNAL_SERVER_ERROR"
            assert "secret-token" not in failed.model_dump_json() + caplog.text
            with queue.sessions() as session:
                media = session.query(MediaFile).one()
                assert queue.library.files.exists(media.storage_key)
        finally:
            assert manager.stop()
        # Completion commits before successful TEMP cleanup; join the worker first.
        # Equal submission timestamps are ordered by UUID, not input position.
        failed_path = next(path for path in adapter.paths if "-bad_" in path.name)
        successful_path = next(path for path in adapter.paths if "-good_" in path.name)
        assert not failed_path.parent.exists()
        assert not successful_path.parent.exists()


def test_persisted_payload_revalidated_and_credentials_not_saved(queue: QueueService) -> None:
    job = queue.submit([payload(URL + "&token=secret&cookies=private#secret")])[0]
    with queue.sessions() as session:
        saved = session.get(Job, job.id)
        assert saved.payload_json["url"] == URL
    with queue.sessions.begin() as session:
        session.add(
            Job(
                type="download",
                payload_json={"url": URL, "max_height": 1080, "command": "unsafe shell"},
            )
        )
    queue.cancel(job.id)
    claim = queue.claim()
    assert claim is not None
    execute_download(queue, claim, Event())
    assert queue.get(claim.id).error.code == "INVALID_JOB_PAYLOAD"


def test_lifespan_recovers_before_start_and_cancels_on_shutdown(
    db_engine: Engine, settings: Settings, local_media: Path, tmp_path: Path
) -> None:
    settings = settings.model_copy(
        update={"temp_storage_root": tmp_path / "temp", "download_concurrency": 1}
    )
    adapter = ControlledAdapter(local_media)
    downloader = DownloaderService(settings, {Platform.YOUTUBE: adapter})
    old = datetime.now(UTC) - timedelta(minutes=2)
    with create_session_factory(db_engine).begin() as session:
        job = Job(
            type="download",
            status=S.DOWNLOADING,
            attempt_count=1,
            payload_json=payload().model_dump(),
            heartbeat_at=old,
            started_at=old,
        )
        session.add(job)
        session.flush()
        job_id = job.id
    app = create_app(settings, downloader=downloader)
    manager = app.state.worker_manager
    with TestClient(app) as client:
        adapter.wait_started(1)
        assert client.get(f"/api/v1/jobs/{job_id}").json()["attempt_count"] == 2
        with pytest.raises(ConflictError):
            manager.start()
        manager.cancel(job_id)
        adapter.release.set()
        wait_status(manager.queue, job_id, S.CANCELLED)
    assert manager.supervisor is not None and not manager.supervisor.is_alive()
    assert all(not thread.is_alive() for thread in manager.threads)
    assert app.state.engine.pool.checkedout() == 0


def test_bounded_shutdown_retains_supervision_until_blocking_call_returns(
    queue: QueueService, settings: Settings, local_media: Path, tmp_path: Path
) -> None:
    adapter = controlled(queue, settings, local_media, tmp_path)
    job = queue.submit([payload()])[0]
    stopped = Event()
    manager = WorkerManager(
        queue, 1, poll_seconds=0.01, heartbeat_seconds=0.01, on_stopped=stopped.set
    )
    manager.start()
    try:
        adapter.wait_started(1)
        assert not manager.stop(timeout=0.01)
        assert not stopped.is_set()
        assert queue.get(job.id).status == S.DOWNLOADING
        adapter.release.set()
        assert stopped.wait(5)
        assert manager.stop()
        assert queue.get(job.id).status == S.CANCELLED
        assert not adapter.paths[0].parent.exists()
    finally:
        adapter.release.set()
        manager.stop()


def test_api_submission_poll_cancel_retry_pause_and_resume(
    db_engine: Engine, settings: Settings, local_media: Path, tmp_path: Path
) -> None:
    settings = settings.model_copy(
        update={"temp_storage_root": tmp_path / "temp", "download_concurrency": 1}
    )
    adapter = ControlledAdapter(local_media)
    app = create_app(settings, downloader=DownloaderService(settings, {Platform.YOUTUBE: adapter}))
    with TestClient(app) as client:
        assert client.post("/api/v1/queue/pause").json() == {"paused": True}
        response = client.post("/api/v1/downloads", json={"urls": [URL, URL + "-bad"]})
        assert response.status_code == 202
        jobs = response.json()["jobs"]
        assert [job["status"] for job in jobs] == ["queued", "queued"]
        listed = client.get("/api/v1/jobs?status=queued&type=download&page_size=1").json()
        assert listed["total"] == 2 and len(listed["items"]) == 1
        view = client.get(f"/api/v1/jobs/{jobs[0]['id']}").json()
        assert "payload_json" not in view and "url" not in str(view)
        assert client.post(f"/api/v1/jobs/{jobs[0]['id']}/cancel").json()["status"] == "cancelled"
        assert client.post(f"/api/v1/jobs/{jobs[0]['id']}/retry").status_code == 409
        assert client.post("/api/v1/queue/resume").json() == {"paused": False}
        adapter.wait_started(1)
        assert client.get("/api/v1/health").status_code == 200
        adapter.release.set()
        wait_status(app.state.worker_manager.queue, jobs[1]["id"], S.FAILED)
        assert client.post("/api/v1/queue/pause").status_code == 200
        assert client.post(f"/api/v1/jobs/{jobs[1]['id']}/retry").json()["status"] == "queued"
        assert client.get("/api/v1/jobs?status=failed").json()["total"] == 0
        for suffix in ("", "/cancel", "/retry"):
            result = (
                client.get("/api/v1/jobs/missing")
                if not suffix
                else client.post("/api/v1/jobs/missing" + suffix)
            )
            assert result.status_code == 404 and result.json()["error"]["code"] == "NOT_FOUND"
        response = client.post("/api/v1/downloads", json={"urls": [URL + "-success"]})
        successful = response.json()["jobs"][0]["id"]
        client.post("/api/v1/queue/resume")
        wait_status(app.state.worker_manager.queue, successful, S.COMPLETED)
        for suffix in ("cancel", "retry"):
            assert client.post(f"/api/v1/jobs/{successful}/{suffix}").status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {"urls": []},
        {"urls": [URL] * 101},
        {"urls": [URL], "max_height": 1081},
        {"urls": [URL], "storage_target": "unsupported"},
        {"urls": [URL], "force": "true"},
        {"urls": [URL], "command": "unsafe"},
        {"urls": [URL, "file:///private"]},
        {"urls": ["https://user:password@youtube.com/watch?v=id"]},
        {"urls": [URL], "audio_enabled": "yes"},
    ],
)
def test_api_invalid_input_never_creates_jobs(
    db_engine: Engine, settings: Settings, body: dict
) -> None:
    app = create_app(settings, start_workers=False)
    with TestClient(app) as client:
        response = client.post("/api/v1/downloads", json=body)
        assert response.status_code == 422
        assert client.get("/api/v1/jobs").json()["total"] == 0


def test_app_start_requires_migration_and_releases_engine(settings: Settings) -> None:
    app = create_app(settings)
    with pytest.raises(OperationalError):
        with TestClient(app):
            pass
    assert app.state.worker_manager.threads == []
    assert app.state.engine.pool.checkedout() == 0


def test_partial_thread_start_failure_leaks_no_threads(
    db_engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(settings)
    start = Thread.start

    def fail_second_worker(thread: Thread) -> None:
        if thread.name == "videovault-worker-1":
            raise RuntimeError("simulated thread resource exhaustion")
        start(thread)

    monkeypatch.setattr(Thread, "start", fail_second_worker)
    with pytest.raises(RuntimeError, match="resource exhaustion"):
        with TestClient(app):
            pass
    manager = app.state.worker_manager
    assert all(not thread.is_alive() for thread in manager.threads)
    assert manager.supervisor is not None and not manager.supervisor.is_alive()
    assert app.state.engine.pool.checkedout() == 0


def test_owned_blocked_attempt_is_not_recovered_when_heartbeat_fails(
    queue: QueueService,
    settings: Settings,
    local_media: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = controlled(queue, settings, local_media, tmp_path)
    job = queue.submit([payload()])[0]
    manager = WorkerManager(queue, 2, poll_seconds=0.01)
    manager.start()
    try:
        adapter.wait_started(1)
        queue.clock = lambda: datetime.now(UTC) + timedelta(minutes=2)

        def unavailable(_):
            raise OperationalError("heartbeat", {}, RuntimeError("busy"))

        monkeypatch.setattr(queue, "heartbeat", unavailable)
        manager.tick()
        assert queue.get(job.id).status == S.DOWNLOADING
        assert queue.get(job.id).attempt_count == 1
        assert adapter.started == 1
        adapter.release.set()
        wait_status(queue, job.id, S.CANCELLED)
    finally:
        adapter.release.set()
        assert manager.stop()


@pytest.mark.parametrize("failure", ["authentication", "missing_tool", "invalid_media"])
def test_domain_failures_persist_without_automatic_retry(
    queue: QueueService,
    settings: Settings,
    local_media: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    adapter = controlled(queue, settings, local_media, tmp_path)
    adapter.release.set()
    if failure == "authentication":

        def restricted(url: str):
            raise AuthenticationRequiredError()

        monkeypatch.setattr(adapter, "resolve", restricted)
        code = "AUTHENTICATION_REQUIRED"
    elif failure == "missing_tool":
        monkeypatch.setattr(probe.shutil, "which", lambda name: None)
        code = "MEDIA_TOOL_UNAVAILABLE"
    else:
        invalid = tmp_path / "invalid.mp4"
        invalid.write_bytes(b"invalid media")
        adapter.media = invalid
        code = "MEDIA_VALIDATION_FAILED"
    queue.submit([payload()])
    claim = queue.claim()
    assert claim is not None
    execute_download(queue, claim, Event())
    job = queue.get(claim.id)
    assert job.status == S.FAILED and job.error.code == code
    assert job.progress_percent < 100 and job.completed_at is not None
    assert job.attempt_count == 1 and queue.claim() is None
    assert not list((tmp_path / "temp").glob("*"))
