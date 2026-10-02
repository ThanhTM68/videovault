from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import create_session_factory
from app.models import Download, Job, Video
from app.models.enums import DownloadStatus, JobStatus, Platform, StorageProvider
from app.repositories.downloads import DownloadRepository
from app.repositories.jobs import JobRepository
from app.repositories.media_files import MediaFileRepository
from app.repositories.videos import VideoRepository
from tests.factories import make_media, make_video


def test_video_repository_crud(db_session: Session) -> None:
    repository = VideoRepository(db_session)
    video = repository.add(make_video())
    assert repository.get_by_id(video.id) is video
    assert repository.get_by_platform_identity(Platform.YOUTUBE, "video-1") is video
    assert repository.get_by_platform_identity(Platform.TIKTOK, "video-1") is None
    assert repository.get_by_id("missing") is None
    video.title = "Updated"
    video.metadata_json["extra"] = "value"
    db_session.commit()
    db_session.expire_all()
    assert repository.get_by_id(video.id).title == "Updated"
    assert video.metadata_json == {"extra": "value"}
    repository.delete(video)
    db_session.commit()
    assert repository.get_by_id(video.id) is None


def test_download_repository_history_and_crud(db_session: Session) -> None:
    video = VideoRepository(db_session).add(make_video())
    other = VideoRepository(db_session).add(make_video("other"))
    repository = DownloadRepository(db_session)
    created = datetime(2026, 1, 1, tzinfo=UTC)
    first = repository.add(
        Download(video_id=video.id, status=DownloadStatus.COMPLETED, created_at=created)
    )
    forced = repository.add(
        Download(
            video_id=video.id,
            status=DownloadStatus.COMPLETED,
            forced=True,
            created_at=created + timedelta(seconds=1),
        )
    )
    failed = repository.add(Download(video_id=video.id, status=DownloadStatus.FAILED))
    repository.add(Download(video_id=video.id, status=DownloadStatus.SKIPPED_DUPLICATE))
    repository.add(Download(video_id=other.id, status=DownloadStatus.COMPLETED))
    assert repository.list_successful_for_video(video.id) == [first, forced]
    assert repository.get_by_id(failed.id) is failed
    assert repository.get_by_id("missing") is None
    failed.failure_code = "TEST_FAILURE"
    db_session.commit()
    db_session.expire_all()
    assert repository.get_by_id(failed.id).failure_code == "TEST_FAILURE"
    repository.delete(first)
    db_session.commit()
    assert repository.list_successful_for_video(video.id) == [forced]


def test_job_repository_crud(db_session: Session) -> None:
    repository = JobRepository(db_session)
    job = repository.add(Job(type="download", payload_json={"urls": ["https://example.com"]}))
    assert repository.get_by_id(job.id) is job
    assert repository.get_by_id("missing") is None
    repository.update_state(job, status=JobStatus.DOWNLOADING, progress_percent=25)
    job.attempt_count = 1
    db_session.commit()
    db_session.expire_all()
    assert job.status == JobStatus.DOWNLOADING
    assert job.progress_percent == 25
    assert job.attempt_count == 1
    repository.delete(job)
    db_session.commit()
    assert repository.get_by_id(job.id) is None


def test_media_repository_crud(db_session: Session) -> None:
    video = VideoRepository(db_session).add(make_video())
    repository = MediaFileRepository(db_session)
    media = repository.add(make_media(video))
    assert repository.get_by_id(media.id) is media
    assert repository.list_for_video(video.id) == [media]
    assert repository.get_by_id("missing") is None
    media.storage_provider = StorageProvider.GOOGLE_DRIVE
    media.storage_key = "drive-file-id"
    db_session.commit()
    db_session.expire_all()
    assert media.storage_key == "drive-file-id"
    repository.delete(media)
    db_session.commit()
    assert repository.get_by_id(media.id) is None
    assert db_session.get(Video, video.id) is video


def test_repositories_do_not_commit_and_rollback_recovers(
    db_session: Session, db_engine: Engine
) -> None:
    repository = VideoRepository(db_session)
    repository.add(make_video())
    with create_session_factory(db_engine)() as observer:
        assert observer.scalars(select(Video)).all() == []
    with pytest.raises(IntegrityError):
        repository.add(make_video())
    db_session.rollback()
    assert repository.get_by_platform_identity(Platform.YOUTUBE, "video-1") is None
    repository.add(make_video("after-rollback"))
    db_session.commit()
    with create_session_factory(db_engine)() as observer:
        assert [video.platform_video_id for video in observer.scalars(select(Video))] == [
            "after-rollback"
        ]
