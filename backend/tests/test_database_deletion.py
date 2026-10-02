from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Collection,
    CollectionVideo,
    Creator,
    Download,
    Job,
    MediaFile,
    StorageAccount,
    Tag,
    Video,
    VideoTag,
)
from app.models.enums import DownloadStatus, Platform, StorageProvider
from app.repositories.downloads import DownloadRepository
from app.repositories.media_files import MediaFileRepository
from app.repositories.videos import VideoRepository
from tests.factories import make_media, make_video


@pytest.mark.parametrize("load_children", [False, True])
def test_creator_and_job_deletion_preserve_records(
    db_session: Session, load_children: bool
) -> None:
    creator = Creator(platform=Platform.YOUTUBE)
    job = Job(type="download")
    video = make_video()
    video.creator = creator
    download = Download(video=video, job=job)
    db_session.add(download)
    db_session.commit()
    creator_id, job_id = creator.id, job.id
    db_session.expire_all()
    if load_children:
        assert creator.videos == [video]
        assert job.downloads == [download]
    db_session.delete(creator)
    db_session.delete(job)
    db_session.commit()
    assert db_session.get(Creator, creator_id) is None
    assert db_session.get(Job, job_id) is None
    assert video.creator_id is None
    assert download.job_id is None
    assert db_session.get(Video, video.id) is video
    assert db_session.get(Download, download.id) is download


@pytest.mark.parametrize("load_children", [False, True])
def test_history_removal_preserves_media_and_files(
    db_session: Session, tmp_path: Path, load_children: bool
) -> None:
    video = VideoRepository(db_session).add(make_video())
    history = DownloadRepository(db_session)
    download = history.add(Download(video_id=video.id, status=DownloadStatus.COMPLETED))
    path = tmp_path / "sample.mp4"
    path.write_bytes(b"test fixture")
    media = make_media(video, download)
    media.storage_key = str(path)
    db_session.add(media)
    db_session.commit()
    db_session.expire_all()
    if load_children:
        assert download.media_files == [media]
    history.delete(download)
    db_session.commit()
    assert history.list_successful_for_video(video.id) == []
    assert db_session.get(MediaFile, media.id) is media
    assert media.download_id is None
    assert media.storage_key == str(path)
    assert path.read_bytes() == b"test fixture"
    MediaFileRepository(db_session).delete(media)
    db_session.commit()
    assert db_session.get(Video, video.id) is video
    assert path.exists()


@pytest.mark.parametrize("child", ["download", "media"])
@pytest.mark.parametrize("load_children", [False, True])
def test_video_deletion_is_restricted_with_history_or_media(
    db_session: Session, child: str, load_children: bool
) -> None:
    repository = VideoRepository(db_session)
    video = repository.add(make_video())
    if child == "download":
        db_session.add(Download(video_id=video.id))
    else:
        db_session.add(make_media(video))
    db_session.commit()
    db_session.expire_all()
    if load_children:
        assert video.downloads if child == "download" else video.media_files
    with pytest.raises(IntegrityError):
        repository.delete(video)
    db_session.rollback()
    assert repository.get_by_id(video.id) is video
    assert len(video.downloads if child == "download" else video.media_files) == 1


@pytest.mark.parametrize("remove", ["collection", "tag", "video", "association"])
def test_association_deletion_never_deletes_other_entities(
    db_session: Session, remove: str
) -> None:
    video = VideoRepository(db_session).add(make_video())
    collection, tag = Collection(name="Research"), Tag(name="research")
    db_session.add_all([collection, tag])
    db_session.flush()
    link = CollectionVideo(collection_id=collection.id, video_id=video.id)
    tag_link = VideoTag(video_id=video.id, tag_id=tag.id)
    db_session.add_all([link, tag_link])
    db_session.commit()
    entities = {"collection": collection, "tag": tag, "video": video, "association": link}
    db_session.delete(entities[remove])
    db_session.commit()
    assert (
        db_session.get(Video, video.id) is None
        if remove == "video"
        else db_session.get(Video, video.id) is video
    )
    if remove != "collection":
        assert db_session.get(Collection, collection.id) is collection
    if remove != "tag":
        assert db_session.get(Tag, tag.id) is tag
    assert len(db_session.scalars(select(CollectionVideo)).all()) == (
        0 if remove in ("collection", "video", "association") else 1
    )
    assert len(db_session.scalars(select(VideoTag)).all()) == (
        0 if remove in ("tag", "video") else 1
    )


def test_storage_account_deletion_does_not_delete_media(db_session: Session) -> None:
    video = VideoRepository(db_session).add(make_video())
    media = make_media(video)
    account = StorageAccount(provider=StorageProvider.LOCAL, display_name="Local")
    db_session.add_all([media, account])
    db_session.commit()
    db_session.delete(account)
    db_session.commit()
    assert db_session.get(MediaFile, media.id) is media
