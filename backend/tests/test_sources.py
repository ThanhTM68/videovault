from copy import deepcopy
from threading import Event

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select

from app.application import create_app
from app.db.session import create_session_factory
from app.models import Download, Job, MediaFile, Video
from app.models.enums import JobStatus as S
from app.models.enums import Platform
from app.models.enums import StorageProvider as P
from app.schemas.sources import BatchDownloadRequest, SourceResolveRequest
from app.services.downloader.service import DownloaderService
from app.services.downloader.source_ytdlp import SourceYtDlp
from app.services.queue.models import DownloadPayload
from app.services.queue.service import QueueService
from app.services.sources.adapters import SourceAdapterRegistry, YouTubeSourceAdapter
from app.services.sources.errors import SourceError
from app.services.sources.service import SourceService
from app.services.sources.urls import source_url
from app.workers.download_worker import execute_download
from tests.source_fixtures import CHANNEL, DATA, IDS, SOURCE, SourceCore, entry
from tests.test_queue import ControlledAdapter, wait_status
from tests.test_storage import (
    drive_queue,  # noqa: F401 -- reuse isolated real fake-Drive integration
)


@pytest.fixture
def source_service(db_engine, settings, local_media):
    adapter = ControlledAdapter(local_media)
    adapter.release.set()
    queue = QueueService(
        create_session_factory(db_engine), DownloaderService(settings, {Platform.YOUTUBE: adapter})
    )
    core = SourceCore()
    service = SourceService(queue, SourceAdapterRegistry((YouTubeSourceAdapter(core),)))
    return service, core


def preview(service, **kwargs):
    return service.resolve(SourceResolveRequest(**({"url": SOURCE} | kwargs)))


def submit(service, identities=None, **kwargs):
    result = preview(service)
    return service.submit(
        BatchDownloadRequest(
            preview_id=result.preview_id, selected_ids=identities or IDS[:2], **kwargs
        )
    )


def run_jobs(queue):
    while claim := queue.claim():
        execute_download(queue, claim, Event())


@pytest.mark.parametrize(
    "url",
    [
        "https://youtube.com/@research",
        SOURCE,
        "https://m.youtube.com/@research/videos/",
        "https://www.youtube.com/channel/" + CHANNEL,
        "https://www.youtube.com/channel/" + CHANNEL + "/videos",
    ],
)
def test_exact_source_forms(url):
    assert source_url(url)[0] == Platform.YOUTUBE
    assert source_url(url)[1].endswith("/videos")


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.youtube.com/@research",
        "https://youtube.com/playlist?list=bad",
        "https://youtube.com/watch?v=clip0000001",
        "https://youtu.be/clip0000001",
        "https://youtube.com/@research/shorts",
        "https://youtube.com/results?search_query=test",
        "https://youtube.com/",
        "https://127.0.0.1/@research",
        "https://localhost/@research",
        "file:///secret",
        "https://user:secret@youtube.com/@research",
        "ytsearch:research",
        "https://youtube.com:444/@research",
        "https://youtube.com/@ab",
    ],
)
def test_rejected_source_forms(url):
    with pytest.raises(SourceError):
        source_url(url)


@pytest.mark.parametrize("n", [0, -1, 101, 100000, 2.5, "5", True])
def test_strict_n(n):
    with pytest.raises(ValidationError):
        SourceResolveRequest(url=SOURCE, n=n)


@pytest.mark.parametrize("n", [1, 100])
def test_n_scope_and_identity_dedup(source_service, n):
    service, _ = source_service
    result = preview(service, n=n)
    assert len(result.candidates) == min(n, 4)
    assert result.statistics.duplicate_count == 1 and result.statistics.enumerated_count == 5
    assert result.source.total_available is None
    assert [item.platform_video_id for item in result.candidates] == IDS[:n]


@pytest.mark.parametrize(
    ("filters", "expected", "missing"),
    [
        ({"min_duration": 20}, [IDS[1], IDS[3]], 1),
        ({"max_duration": 20}, IDS[:2], 1),
        ({"min_duration": 10, "max_duration": 20}, IDS[:2], 1),
        ({"min_duration": 20, "max_duration": 20}, [IDS[1]], 1),
        ({"max_duration": 0}, [], 1),
        ({}, IDS, 0),
    ],
)
def test_duration_inclusive_unknown_source_order(source_service, filters, expected, missing):
    service, _ = source_service
    result = preview(service, **filters)
    assert [item.platform_video_id for item in result.candidates] == expected
    assert result.statistics.metadata_unavailable_count == missing
    if not filters:
        item = result.candidates[2]
        assert item.duration_seconds is item.view_count is item.upload_date is None


@pytest.mark.parametrize(
    "options",
    [
        {"ordering": "newest"},
        {"ordering": "oldest"},
        {"ordering": "views"},
        {"min_views": 0},
        {"max_views": 100},
        {"date_from": "2026-01-01"},
        {"date_to": "2026-12-31"},
    ],
)
def test_unsupported_before_network_and_no_jobs(source_service, options):
    service, core = source_service
    with pytest.raises(SourceError) as error:
        preview(service, **options)
    assert error.value.code == (
        "SOURCE_SORT_UNSUPPORTED" if "ordering" in options else "SOURCE_FILTER_UNSUPPORTED"
    )
    assert core.calls == 0 and service.queue.list().total == 0


@pytest.mark.parametrize(
    "options",
    [
        {"min_views": -1},
        {"min_views": 2, "max_views": 1},
        {"min_duration": -1},
        {"min_duration": 2, "max_duration": 1},
        {"min_duration": "1"},
        {"date_from": "2026-02-01", "date_to": "2026-01-01"},
        {"extra": True},
    ],
)
def test_invalid_ranges(options):
    with pytest.raises(ValidationError):
        SourceResolveRequest(url=SOURCE, **options)


@pytest.mark.parametrize(
    "mutation",
    [
        {"url": "https://example.com/video"},
        {"ie_key": "Generic"},
        {"id": "bad"},
        {"url": "https://youtube.com/watch?v=other000001"},
        {"channel_id": "UC" + "b" * 22},
        {"has_drm": True},
        {"availability": "private"},
        {"is_live": True},
        {"_type": "playlist"},
    ],
)
def test_unsafe_candidate_rejected(source_service, mutation):
    service, core = source_service
    core.data["entries"] = [entry(IDS[0], **mutation)]
    result = preview(service)
    assert not result.candidates and result.statistics.rejected_count == 1


def test_wrapper_metadata_only_extractors_bounded_and_sanitized(monkeypatch):
    from app.services.downloader import source_ytdlp

    pulled = []

    class FakeDL:
        def __init__(self, options):
            assert options["allowed_extractors"] == ["^youtube:tab$"]
            assert options["socket_timeout"] == 30 and options["playlistend"] == 100
            assert options["extract_flat"] is True and options["skip_download"] is True
            assert options["lazy_playlist"] is True and options["usenetrc"] is False
            assert not any(
                key in options
                for key in ("cookiefile", "cookiesfrombrowser", "username", "password")
            )

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, **kwargs):
            assert url == SOURCE and kwargs == {"download": False, "process": False}

            def entries():
                for index in range(1000):
                    pulled.append(index)
                    yield entry(
                        f"clip{index:07}", headers={"authorization": "private"}, formats=["private"]
                    )

            return deepcopy(DATA) | {"entries": entries()}

    monkeypatch.setattr(source_ytdlp, "_SourceDL", FakeDL)
    result = SourceYtDlp().list_channel(SOURCE)
    assert len(pulled) == len(result["entries"]) == 100
    assert "private" not in str(result)


def test_history_pre_dedup_force_and_transient_preview(source_service):
    service, core = source_service
    first = submit(service, [IDS[0]])
    run_jobs(service.queue)
    assert service.queue.get(first.jobs[0].id).status == S.COMPLETED
    result = preview(service)
    assert result.candidates[0].has_download_history and result.candidates[0].has_file
    calls = core.calls
    submitted = service.submit(
        BatchDownloadRequest(preview_id=result.preview_id, selected_ids=[IDS[0], IDS[1], IDS[1]])
    )
    assert core.calls == calls  # no source network at submission
    assert (
        submitted.created_count
        == submitted.skipped_history_count
        == submitted.skipped_duplicate_selection_count
        == 1
    )
    assert service.queue.list().total == 2
    run_jobs(service.queue)
    forced = submit(service, [IDS[0]], force=True)
    run_jobs(service.queue)
    assert service.queue.get(forced.jobs[0].id).status == S.COMPLETED
    assert service.queue.library.history(page=1, page_size=100).total == 3


def test_stale_preview_rechecks_history_and_worker_race(source_service):
    service, _ = source_service
    stale = preview(service)
    service.queue.submit([DownloadPayload(url=stale.candidates[0].canonical_url, max_height=1080)])
    run_jobs(service.queue)
    result = service.submit(
        BatchDownloadRequest(preview_id=stale.preview_id, selected_ids=[IDS[0]])
    )
    assert result.created_count == 0 and result.skipped_history_count == 1
    batch = submit(service, [IDS[1]])
    # Another job can win after pre-dedup; worker-level identity history is retained.
    claim = service.queue.claim()
    service.queue.submit(
        [DownloadPayload(url="https://youtube.com/watch?v=" + IDS[1], max_height=1080)]
    )
    run_jobs(service.queue)
    execute_download(service.queue, claim, Event())
    assert service.queue.get(batch.jobs[0].id).status == S.SKIPPED_DUPLICATE


def test_cache_expiry_bound_replay_and_tampering(source_service):
    service, _ = source_service
    for _ in range(35):
        last = preview(service)
    assert len(service.previews) == 32
    with pytest.raises(SourceError) as error:
        service.submit(
            BatchDownloadRequest(preview_id=last.preview_id, selected_ids=["outside0001"])
        )
    assert error.value.code == "BATCH_SELECTION_INVALID" and service.queue.list().total == 0
    request = BatchDownloadRequest(preview_id=last.preview_id, selected_ids=[IDS[0]])
    service.submit(request)
    with pytest.raises(SourceError) as error:
        service.submit(request)
    assert error.value.code == "SOURCE_PREVIEW_EXPIRED"
    new = preview(service)
    service.clock = lambda: float("inf")
    with pytest.raises(SourceError):
        service.submit(BatchDownloadRequest(preview_id=new.preview_id, selected_ids=[IDS[0]]))


def test_drive_batch_integration_and_failure_atomicity(drive_queue):  # noqa: F811
    queue, drive = drive_queue
    service = SourceService(queue, SourceAdapterRegistry((YouTubeSourceAdapter(SourceCore()),)))
    result = submit(service, storage_target=P.GOOGLE_DRIVE)
    assert result.created_count == 2
    run_jobs(queue)
    assert all(queue.get(item.id).status == S.COMPLETED for item in result.jobs)
    with queue.sessions() as session:
        assert set(session.scalars(select(MediaFile.storage_provider))) == {P.GOOGLE_DRIVE}
    queue.storage.connection.disconnect()
    before = queue.list().total
    with pytest.raises(Exception) as error:
        submit(service, [IDS[3]], storage_target=P.GOOGLE_DRIVE)
    assert error.value.code == "STORAGE_NOT_CONNECTED" and queue.list().total == before


def test_api_read_only_preview_strict_submission_and_options(source_service):
    service, _ = source_service
    app = create_app(service.queue.downloader.settings, start_workers=False)
    app.state.source_service = service
    with TestClient(app) as client:
        result = client.post("/api/v1/sources/resolve", json={"url": SOURCE}).json()
        with service.queue.sessions() as session:
            for model in (Video, Download, Job, MediaFile):
                assert session.scalar(select(func.count()).select_from(model)) == 0
        invalid = client.post(
            "/api/v1/sources/batch-download",
            json={
                "preview_id": result["preview_id"],
                "selected_ids": IDS[:1],
                "url": "https://evil.test",
            },
        )
        assert invalid.status_code == 422
        response = client.post(
            "/api/v1/sources/batch-download",
            json={
                "preview_id": result["preview_id"],
                "selected_ids": IDS[:2],
                "max_height": 720,
                "preferred_container": "mkv",
                "audio_enabled": False,
                "storage_target": "local",
                "force": True,
            },
        )
        assert response.status_code == 202 and response.json()["created_count"] == 2
        with service.queue.sessions() as session:
            for job in session.scalars(select(Job)):
                assert job.type == "download" and job.payload_json["max_height"] == 720
                assert (
                    job.payload_json["force"] is True and job.payload_json["audio_enabled"] is False
                )
        assert "url" not in response.text


@pytest.mark.parametrize(
    "url",
    [
        "https://www.tiktok.com/@research",
        "https://www.douyin.com/user/research",
        "https://instagram.com/research",
        "https://www.facebook.com/research",
    ],
)
def test_other_platforms_degrade_honestly(source_service, url):
    service, core = source_service
    with pytest.raises(SourceError) as error:
        preview(service, url=url)
    assert error.value.code == "SOURCE_LIST_UNSUPPORTED" and core.calls == 0


@pytest.mark.parametrize("value", [12345, True, "20260901", "2026-09-01T00:00:00Z"])
def test_dates_require_iso_calendar_day(value):
    with pytest.raises(ValidationError):
        SourceResolveRequest(url=SOURCE, date_from=value)


@pytest.mark.parametrize("ids", [[], IDS * 26, ["x" * 10000], ["../outside!"], [123]])
def test_selection_resource_limits(ids):
    with pytest.raises(ValidationError):
        BatchDownloadRequest(preview_id="p" * 32, selected_ids=ids)


def test_network_budget_deadline_and_extractor_allowlist(monkeypatch):
    from app.services.downloader import source_ytdlp
    from app.services.downloader.ytdlp import _options

    calls = []
    monkeypatch.setattr(
        source_ytdlp.yt_dlp.YoutubeDL, "urlopen", lambda self, req: calls.append(req)
    )
    extractor = source_ytdlp._SourceDL(_options() | {"allowed_extractors": ["^youtube:tab$"]})
    assert set(extractor._ies) == {"YoutubeTab"}
    for _ in range(12):
        extractor.urlopen("fixture")
    with pytest.raises(SourceError):
        extractor.urlopen("fixture")
    assert len(calls) == 12
    extractor._source_requests = 0
    extractor._source_deadline = 0
    with pytest.raises(SourceError):
        extractor.urlopen("fixture")
    assert len(calls) == 12


def test_one_history_query_for_preview_and_submit(source_service):
    from sqlalchemy import event

    service, _ = source_service
    statements = []
    engine = service.queue.sessions.kw["bind"]

    def record(conn, cursor, statement, parameters, context, executemany):
        if "FROM videos" in statement:
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        value = preview(service)
        assert len(statements) == 1
        service.submit(BatchDownloadRequest(preview_id=value.preview_id, selected_ids=IDS))
        assert len(statements) == 2
    finally:
        event.remove(engine, "before_cursor_execute", record)


def test_batch_atomic_rollback_retains_preview(source_service, monkeypatch):
    from app.repositories.jobs import JobRepository

    service, _ = source_service
    value = preview(service)
    original = JobRepository.add
    calls = 0

    def add(repo, job):
        nonlocal calls
        calls += 1
        row = original(repo, job)
        if calls == 2:
            raise RuntimeError("Simulated database failure")
        return row

    with monkeypatch.context() as scoped:
        scoped.setattr(JobRepository, "add", add)
        with pytest.raises(RuntimeError):
            service.submit(BatchDownloadRequest(preview_id=value.preview_id, selected_ids=IDS[:2]))
    assert service.queue.list().total == 0 and value.preview_id in service.previews
    assert (
        service.submit(
            BatchDownloadRequest(preview_id=value.preview_id, selected_ids=IDS[:2])
        ).created_count
        == 2
    )


def test_concurrent_preview_consumption_creates_jobs_once(source_service):
    from concurrent.futures import ThreadPoolExecutor

    service, _ = source_service
    value = preview(service)
    request = BatchDownloadRequest(preview_id=value.preview_id, selected_ids=IDS[:2])

    def run():
        try:
            return service.submit(request).created_count
        except SourceError as error:
            return error.code

    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(lambda _: run(), range(2)))
    assert set(outcomes) == {2, "SOURCE_PREVIEW_EXPIRED"}
    assert service.queue.list().total == 2


def test_batch_jobs_pause_cancel_retry_and_failure_isolation(source_service):
    from app.core.errors import ConflictError
    from app.workers.manager import WorkerManager

    service, core = source_service
    bad_id = "clip0000bad"
    core.data["entries"] = [entry(IDS[0]), entry(bad_id), entry(IDS[1])]
    manager = WorkerManager(service.queue, 1, poll_seconds=0.01)
    manager.pause()
    response = submit(service, [IDS[0], bad_id, IDS[1]])
    assert manager.paused and service.queue.list(status=S.QUEUED).total == 3
    cancel_id = response.jobs[0].id
    assert service.queue.cancel(cancel_id).status == S.CANCELLED
    with pytest.raises(ConflictError):
        service.queue.retry(cancel_id)
    manager.start()
    try:
        manager.resume()
        failed = wait_status(service.queue, response.jobs[1].id, S.FAILED)
        wait_status(service.queue, response.jobs[2].id, S.COMPLETED)
        assert service.queue.get(cancel_id).status == S.CANCELLED
        assert "secret" not in failed.error.message
        manager.pause()
        assert service.queue.retry(failed.id).status == S.QUEUED
        manager.resume()
        assert wait_status(service.queue, failed.id, S.FAILED).attempt_count == 2
    finally:
        assert manager.stop()


@pytest.mark.parametrize(
    "data",
    [
        {"n": 0},
        {"n": 101},
        {"n": True},
        {"ordering": "views"},
        {"min_views": 0},
        {"date_from": "2026-09-01"},
        {"date_from": 12345},
        {"min_duration": -1},
        {"min_duration": 20, "max_duration": 10},
        {"url": "https://www.youtube.com/playlist?list=abc"},
    ],
)
def test_api_invalid_requests_have_no_io_or_writes(source_service, data):
    service, core = source_service
    app = create_app(service.queue.downloader.settings, start_workers=False)
    app.state.source_service = service
    with TestClient(app) as client:
        response = client.post("/api/v1/sources/resolve", json={"url": SOURCE} | data)
    assert response.status_code in {400, 422}
    assert "error" in response.json() and core.calls == service.queue.list().total == 0


@pytest.mark.parametrize(
    "metadata",
    [
        {"channel_id": "UC" + "z" * 22, "id": "UC" + "z" * 22},
        {"webpage_url": "https://youtube.com/@other/videos"},
        {"webpage_url": "https://evil.test/@research"},
    ],
)
def test_mismatched_source_context_rejected(metadata):
    data = deepcopy(DATA) | metadata
    url = "https://www.youtube.com/channel/" + CHANNEL if "channel_id" in metadata else SOURCE
    with pytest.raises(SourceError):
        YouTubeSourceAdapter(SourceCore(data)).resolve_source(url)


def test_preview_busy_and_extractor_failure_sanitized(source_service, monkeypatch):
    from app.services.downloader import source_ytdlp

    service, core = source_service
    service.enumerations.acquire()
    service.enumerations.acquire()
    with pytest.raises(SourceError) as error:
        preview(service)
    assert error.value.code == "SOURCE_BUSY" and core.calls == 0
    service.enumerations.release()
    service.enumerations.release()

    def fail(*args):
        raise RuntimeError("sensitive-extractor-response")

    monkeypatch.setattr(source_ytdlp, "_SourceDL", fail)
    with pytest.raises(SourceError) as error:
        SourceYtDlp().list_channel(SOURCE)
    assert error.value.code == "SOURCE_RESOLVE_FAILED" and "sensitive" not in str(error.value)


def test_pinned_youtube_renderer_has_flat_duration_without_invented_date():
    from yt_dlp.extractor.youtube import YoutubeTabIE

    from app.services.downloader.source_ytdlp import _SourceDL
    from app.services.downloader.ytdlp import _options

    with _SourceDL(_options() | {"allowed_extractors": ["^youtube:tab$"]}) as downloader:
        raw = YoutubeTabIE(downloader)._extract_video(
            {
                "videoId": IDS[0],
                "title": {"simpleText": "Public fixture"},
                "lengthText": {"simpleText": "1:30"},
                "publishedTimeText": {"simpleText": "2 days ago"},
                "viewCountText": {"simpleText": "1.2K views"},
            }
        )
    candidate = YouTubeSourceAdapter(SourceCore())._candidate(raw, None)
    assert candidate.duration_seconds == 90 and candidate.upload_date is None
    assert candidate.view_count == 1200
    assert raw["timestamp"] is None and "formats" not in raw


@pytest.mark.parametrize("mode", ["file", "history"])
def test_batch_dedup_uses_success_history_independently_of_files(source_service, mode):
    service, _ = source_service
    submit(service, IDS[:1])
    run_jobs(service.queue)
    video = service.queue.library.list(page=1, page_size=1).items[0]
    service.queue.library.destroy(video.id, mode)
    value = preview(service)
    assert value.candidates[0].has_download_history == (mode == "file")
    assert value.candidates[0].has_file == (mode == "history")
    outcome = service.submit(
        BatchDownloadRequest(preview_id=value.preview_id, selected_ids=IDS[:1])
    )
    assert outcome.created_count == (mode == "history")
    assert outcome.skipped_history_count == (mode == "file")


def test_maximum_safe_unique_batch_is_bounded_to_100(source_service):
    service, core = source_service
    identities = [f"clip{i:07d}" for i in range(105)]
    core.data["entries"] = [entry(identity) for identity in identities]
    value = preview(service, n=100)
    assert len(value.candidates) == value.statistics.enumerated_count == 100
    result = service.submit(
        BatchDownloadRequest(preview_id=value.preview_id, selected_ids=identities[:100])
    )
    assert result.created_count == service.queue.list().total == 100


def test_batch_drive_multiple_workers_use_existing_pipeline(drive_queue):  # noqa: F811
    from app.workers.manager import WorkerManager

    queue, drive = drive_queue
    # The fixture's global pool-empty assertion is intended for serial I/O tests;
    # another worker or API reader can legitimately own a separate transaction.
    drive.engine = None
    service = SourceService(queue, SourceAdapterRegistry((YouTubeSourceAdapter(SourceCore()),)))
    result = submit(service, storage_target=P.GOOGLE_DRIVE)
    manager = WorkerManager(queue, 2, poll_seconds=0.01)
    manager.start()
    try:
        for job in result.jobs:
            wait_status(queue, job.id, S.COMPLETED)
        assert queue.library.history(page=1, page_size=100).total == 2
    finally:
        assert manager.stop()
