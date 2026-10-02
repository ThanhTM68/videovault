from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import JsonValue
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.models import (
    Collection,
    CollectionVideo,
    Creator,
    Download,
    Job,
    StorageAccount,
    Tag,
    Video,
    VideoTag,
)
from app.models.enums import Platform, StorageProvider
from app.repositories.videos import VideoRepository
from tests.factories import make_media, make_video


def test_foreign_keys_on_every_connection(db_engine: Engine, db_session: Session) -> None:
    with db_engine.connect() as first, db_engine.connect() as second:
        assert first.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert second.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    db_session.add(Download(video_id="missing-video"))
    with pytest.raises(IntegrityError, match="FOREIGN KEY"):
        db_session.flush()


def test_platform_identity_uniqueness(db_session: Session) -> None:
    repository = VideoRepository(db_session)
    repository.add(make_video())
    repository.add(make_video(platform=Platform.TIKTOK))
    db_session.commit()
    with pytest.raises(IntegrityError):
        repository.add(make_video())
    db_session.rollback()
    assert len(db_session.scalars(select(Video)).all()) == 2


def test_creator_nullable_and_reliable_identity_uniqueness(db_session: Session) -> None:
    db_session.add_all(
        [
            Creator(platform=Platform.YOUTUBE),
            Creator(platform=Platform.YOUTUBE),
            Creator(platform=Platform.YOUTUBE, platform_creator_id="creator-1"),
            Creator(platform=Platform.TIKTOK, platform_creator_id="creator-1"),
        ]
    )
    db_session.commit()
    db_session.add(Creator(platform=Platform.YOUTUBE, platform_creator_id="creator-1"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
    assert len(db_session.scalars(select(Creator)).all()) == 4


@pytest.mark.parametrize("association", ["collection", "tag"])
def test_association_pair_uniqueness(db_session: Session, association: str) -> None:
    video = VideoRepository(db_session).add(make_video())
    if association == "collection":
        parent = Collection(name="Research")
        db_session.add(parent)
        db_session.flush()
        db_session.add(CollectionVideo(collection_id=parent.id, video_id=video.id))
    else:
        parent = Tag(name="Research")
        db_session.add(parent)
        db_session.flush()
        db_session.add(VideoTag(tag_id=parent.id, video_id=video.id))
    db_session.commit()
    if association == "collection":
        duplicate = CollectionVideo(collection_id=parent.id, video_id=video.id)
    else:
        duplicate = VideoTag(tag_id=parent.id, video_id=video.id)
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_tag_names_are_unique(db_session: Session) -> None:
    db_session.add_all([Tag(name="research"), Tag(name="research")])
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_ids_and_utc_timestamp_round_trip(db_session: Session) -> None:
    local = datetime(2026, 10, 2, 15, 0, tzinfo=timezone(timedelta(hours=7)))
    video = make_video()
    video.discovered_at = local
    db_session.add(video)
    db_session.commit()
    assert UUID(video.id).version == 4
    db_session.expire_all()
    assert video.discovered_at == datetime(2026, 10, 2, 8, 0, tzinfo=UTC)
    assert video.discovered_at.tzinfo == UTC
    raw = db_session.execute(text("SELECT discovered_at FROM videos")).scalar_one()
    assert str(raw).startswith("2026-10-02 08:00:00")
    job = Job(type="download")
    db_session.add(job)
    db_session.flush()
    db_session.refresh(job)
    assert job.created_at.tzinfo == UTC


def test_naive_timestamps_are_rejected(db_session: Session) -> None:
    video = make_video()
    video.discovered_at = datetime(2026, 10, 2)
    db_session.add(video)
    with pytest.raises(StatementError, match="timezone-aware"):
        db_session.flush()


def test_large_counts_and_file_sizes_round_trip(db_session: Session) -> None:
    video = make_video()
    video.view_count = 5_000_000_000
    VideoRepository(db_session).add(video)
    media = make_media(video)
    media.size_bytes = 6_000_000_000
    db_session.add(media)
    db_session.commit()
    db_session.expire_all()
    assert video.view_count == 5_000_000_000
    assert media.size_bytes == 6_000_000_000


@pytest.mark.parametrize(
    ("model", "field"),
    [
        ("video", "platform"),
        ("download", "status"),
        ("job", "status"),
        ("media", "kind"),
        ("media", "storage_provider"),
        ("account", "provider"),
    ],
)
def test_enum_validation_and_database_checks(db_session: Session, model: str, field: str) -> None:
    video = VideoRepository(db_session).add(make_video())
    objects = {
        "video": video,
        "download": Download(video_id=video.id),
        "job": Job(type="download"),
        "media": make_media(video),
        "account": StorageAccount(provider=StorageProvider.LOCAL, display_name="Local"),
    }
    item = objects[model]
    db_session.add(item)
    db_session.commit()
    # Identifiers are hardcoded from model metadata, never user input.
    table = item.__tablename__
    with pytest.raises(IntegrityError, match="CHECK constraint"):
        db_session.execute(
            text(f"UPDATE {table} SET {field} = :value WHERE id = :id"),
            {"value": "invalid-value", "id": item.id},
        )
    db_session.rollback()
    setattr(item, field, "invalid-value")
    with pytest.raises(StatementError):
        db_session.flush()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("platform_video_id", " "),
        ("duration_seconds", -1),
        ("view_count", -1),
        ("width", 0),
        ("height", -1),
        ("fps", 0),
    ],
)
def test_video_numeric_and_identity_checks(
    db_session: Session, field: str, value: str | int
) -> None:
    video = make_video()
    setattr(video, field, value)
    db_session.add(video)
    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("progress_percent", -1),
        ("progress_percent", 101),
        ("attempt_count", -1),
        ("max_attempts", 0),
    ],
)
def test_job_numeric_checks(db_session: Session, field: str, value: int) -> None:
    job = Job(type="download")
    setattr(job, field, value)
    db_session.add(job)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_storage_account_config_is_nonsecret_and_independent(db_session: Session) -> None:
    first = StorageAccount(provider=StorageProvider.LOCAL, display_name="Local")
    second = StorageAccount(provider=StorageProvider.GOOGLE_DRIVE, display_name="Drive")
    db_session.add_all([first, second])
    db_session.flush()
    first.config_json["root_path"] = "D:/VideoVault"
    second.config_json["root_folder_id"] = "folder-id"
    db_session.commit()
    db_session.expire_all()
    assert first.config_json == {"root_path": "D:/VideoVault"}
    assert second.config_json == {"root_folder_id": "folder-id"}


@pytest.mark.parametrize(
    "config",
    [
        {"access_token": "test-only-secret"},
        {"client_secret": "test-only-secret"},
        {"root_path": {"nested": "value"}},
    ],
)
def test_secret_or_nested_storage_config_is_rejected(
    db_session: Session, config: dict[str, JsonValue]
) -> None:
    db_session.add(
        StorageAccount(provider=StorageProvider.LOCAL, display_name="Local", config_json=config)
    )
    with pytest.raises(StatementError):
        db_session.flush()
