import json
from datetime import datetime

from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import Exists

from app.db.base import utc_now
from app.models import (
    Collection,
    CollectionVideo,
    Creator,
    Download,
    MediaFile,
    Tag,
    Video,
    VideoTag,
)
from app.models.enums import DownloadStatus as D
from app.models.enums import MediaKind, Platform
from app.repositories.videos import VideoRepository
from app.services.downloader.models import NormalizedVideo
from app.services.downloader.service import DownloadResult
from app.services.queue.models import Claim, DownloadPayload
from app.services.storage.contracts import StoredObject


class LibraryRepository(VideoRepository):
    def reserve_video(self, video_id: str) -> bool:
        """Own the SQLite writer before reading a membership mutation's snapshot."""
        return (
            self.session.scalar(
                update(Video)
                .where(Video.id == video_id)
                .values(canonical_url=Video.canonical_url)
                .returning(Video.id)
            )
            is not None
        )

    def identity_states(
        self, platform: Platform, identities: list[str]
    ) -> dict[str, tuple[bool, bool]]:
        rows = self.session.execute(
            select(Video.platform_video_id, self.history_exists(), self.file_exists()).where(
                Video.platform == platform, Video.platform_video_id.in_(identities)
            )
        )
        return {identity: (bool(history), bool(file)) for identity, history, file in rows}

    def upsert(self, metadata: NormalizedVideo) -> Video:
        creator_id = None
        if metadata.creator_id:
            self.session.execute(
                insert(Creator)
                .values(
                    platform=metadata.platform,
                    platform_creator_id=metadata.creator_id,
                    name=metadata.creator,
                    canonical_url=metadata.creator_url,
                )
                .on_conflict_do_nothing(index_elements=["platform", "platform_creator_id"])
            )
            creator = self.session.scalar(
                select(Creator).where(
                    Creator.platform == metadata.platform,
                    Creator.platform_creator_id == metadata.creator_id,
                )
            )
            if metadata.creator:
                creator.name = metadata.creator
            if metadata.creator_url:
                creator.canonical_url = metadata.creator_url
            creator_id = creator.id
        self.session.execute(
            insert(Video)
            .values(
                platform=metadata.platform,
                platform_video_id=metadata.platform_video_id,
                canonical_url=metadata.canonical_url,
            )
            .on_conflict_do_nothing(index_elements=["platform", "platform_video_id"])
        )
        video = self.get_by_platform_identity(metadata.platform, metadata.platform_video_id)
        for field in (
            "canonical_url",
            "title",
            "description",
            "duration_seconds",
            "upload_date",
            "view_count",
            "like_count",
            "comment_count",
            "width",
            "height",
            "fps",
            "thumbnail_url",
        ):
            value = getattr(metadata, field)
            if value is not None and value != "":
                setattr(video, field, value)
        if creator_id:
            video.creator_id = creator_id
        video.metadata_json = {**video.metadata_json, **metadata.raw_metadata}
        if metadata.creator:
            video.metadata_json = {**video.metadata_json, "creator_name": metadata.creator}
        video.last_refreshed_at = utc_now()
        self.session.flush()
        return video

    @staticmethod
    def history_exists() -> Exists:
        return exists().where(Download.video_id == Video.id, Download.status == D.COMPLETED)

    @staticmethod
    def file_exists() -> Exists:
        return exists().where(
            MediaFile.video_id == Video.id,
            MediaFile.deleted_at.is_(None),
            MediaFile.missing_at.is_(None),
        )

    def has_history(self, video_id: str) -> bool:
        return bool(
            self.session.scalar(
                select(
                    exists().where(
                        Download.video_id == video_id,
                        Download.status == D.COMPLETED,
                    )
                )
            )
        )

    def page(
        self,
        *,
        page: int,
        page_size: int,
        search: str = "",
        platform: Platform | None = None,
        has_file: bool | None = None,
        has_download_history: bool | None = None,
        tag_id: str | None = None,
        collection_id: str | None = None,
    ) -> tuple[list[Video], int]:
        filters = []
        if search:
            term = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            creator = select(Creator.id).where(
                or_(Creator.name.ilike(term, escape="\\"), Creator.handle.ilike(term, escape="\\"))
            )
            filters.append(
                or_(
                    Video.title.ilike(term, escape="\\"),
                    Video.creator_id.in_(creator),
                    Video.metadata_json["creator_name"].as_string().ilike(term, escape="\\"),
                )
            )
        if platform is not None:
            filters.append(Video.platform == platform)
        if has_file is not None:
            filters.append(self.file_exists() == has_file)
        if has_download_history is not None:
            filters.append(self.history_exists() == has_download_history)
        if tag_id:
            filters.append(Video.id.in_(select(VideoTag.video_id).where(VideoTag.tag_id == tag_id)))
        if collection_id:
            filters.append(
                Video.id.in_(
                    select(CollectionVideo.video_id).where(
                        CollectionVideo.collection_id == collection_id
                    )
                )
            )
        total = self.session.scalar(select(func.count()).select_from(Video).where(*filters)) or 0
        rows = self.session.scalars(
            select(Video)
            .where(*filters)
            .order_by(Video.discovered_at.desc(), Video.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), total

    def named(self, video_id: str, kind: str) -> list[Tag] | list[Collection]:
        if kind == "tags":
            return list(
                self.session.scalars(
                    select(Tag)
                    .join(VideoTag)
                    .where(VideoTag.video_id == video_id)
                    .order_by(Tag.name)
                )
            )
        return list(
            self.session.scalars(
                select(Collection)
                .join(CollectionVideo)
                .where(CollectionVideo.video_id == video_id)
                .order_by(Collection.name)
            )
        )

    def files(self, video_id: str) -> list[MediaFile]:
        return list(
            self.session.scalars(
                select(MediaFile)
                .where(MediaFile.video_id == video_id)
                .order_by(MediaFile.created_at.desc(), MediaFile.id)
            )
        )

    def history(
        self,
        *,
        page: int,
        page_size: int,
        video_id: str | None = None,
        status: D | None = None,
        platform: Platform | None = None,
    ) -> tuple[list[Download], int]:
        filters = []
        if video_id:
            filters.append(Download.video_id == video_id)
        if status:
            filters.append(Download.status == status)
        if platform:
            filters.append(Video.platform == platform)
        query = select(Download).join(Video).where(*filters)
        total = self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        return list(
            self.session.scalars(
                query.order_by(Download.created_at.desc(), Download.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ), total

    def start_attempt(self, video_id: str, claim: Claim, payload: DownloadPayload) -> Download:
        row = Download(
            video_id=video_id,
            job_id=claim.id,
            attempt_number=claim.attempt,
            status=D.DOWNLOADING,
            started_at=utc_now(),
            forced=payload.force,
            requested_quality=json.dumps(
                {k: v for k, v in payload.model_dump().items() if k != "url"}, separators=(",", ":")
            ),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def save_result(self, event_id: str, result: DownloadResult, final: StoredObject) -> None:
        event = self.session.get(Download, event_id)
        if event is None:
            raise ValueError("Download event missing")
        event.status = D.COMPLETED
        event.completed_at = utc_now()
        self.session.add(
            MediaFile(
                video_id=event.video_id,
                download_id=event.id,
                storage_provider=final.provider,
                storage_key=final.key,
                file_name=final.file_name,
                mime_type=final.mime_type,
                size_bytes=final.size,
                sha256=final.sha256,
                width=result.probe.width,
                height=result.probe.height,
                duration_seconds=result.probe.duration_seconds,
                kind=MediaKind.ORIGINAL,
                exists_last_checked_at=utc_now(),
            )
        )
        self.session.flush()

    def close_attempts(
        self,
        job_id: str,
        attempt: int,
        *,
        cancelled: bool,
        code: str | None,
        message: str | None,
        now: datetime,
    ) -> None:
        self.session.execute(
            update(Download)
            .where(
                Download.job_id == job_id,
                Download.attempt_number == attempt,
                Download.status == D.DOWNLOADING,
            )
            .values(
                status=D.CANCELLED if cancelled else D.FAILED,
                completed_at=now,
                failure_code=None if cancelled else code,
                failure_message=None if cancelled else message,
            )
        )

    def remove_history(self, video_id: str) -> None:
        self.session.execute(delete(Download).where(Download.video_id == video_id))

    def reconcile(self, changes: list[tuple[str, bool]]) -> None:
        for media_id, missing in changes:
            self.session.execute(
                update(MediaFile)
                .where(MediaFile.id == media_id, MediaFile.deleted_at.is_(None))
                .values(missing_at=utc_now() if missing else None, exists_last_checked_at=utc_now())
            )

    def mark_deleted(self, media_id: str) -> None:
        self.session.execute(
            update(MediaFile)
            .where(MediaFile.id == media_id)
            .values(deleted_at=utc_now(), exists_last_checked_at=utc_now())
        )


class OrganizationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, kind: str) -> list[Collection | Tag]:
        model = Tag if kind == "tags" else Collection
        return list(self.session.scalars(select(model).order_by(model.name).limit(1000)))

    def create(self, kind: str, name: str) -> Collection | Tag:
        if kind == "tags":
            # Personal tag API uses normalized casefold names; source hashtags stay metadata.
            name = name.casefold()
            self.session.execute(
                insert(Tag).values(name=name).on_conflict_do_nothing(index_elements=["name"])
            )
            return self.session.scalar(select(Tag).where(Tag.name == name))
        item = Collection(name=name)
        self.session.add(item)
        self.session.flush()
        return item

    def attach(self, kind: str, item_id: str, video_id: str, *, remove: bool = False) -> bool:
        model, association = (Tag, VideoTag) if kind == "tags" else (Collection, CollectionVideo)
        if self.session.get(model, item_id) is None:
            return False
        values = {"tag_id" if kind == "tags" else "collection_id": item_id, "video_id": video_id}
        if remove:
            self.session.execute(delete(association).filter_by(**values))
        else:
            self.session.execute(insert(association).values(**values).on_conflict_do_nothing())
        return True
