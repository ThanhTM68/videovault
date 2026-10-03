from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ConflictError, NotFoundError
from app.db.base import utc_now
from app.models import Download, Video
from app.repositories.jobs import JobRepository
from app.repositories.library import LibraryRepository, OrganizationRepository
from app.schemas.library import (
    FileSummary,
    HistoryItem,
    HistoryPage,
    LibraryVideo,
    NamedItem,
    VideoDetail,
    VideoPage,
)
from app.services.downloader.cancellation import DownloadCancelledError
from app.services.downloader.models import NormalizedVideo
from app.services.library.locks import identity_lock
from app.services.queue.models import Claim, DownloadPayload
from app.services.storage.service import StorageService

logger = logging.getLogger(__name__)


class LibraryService:
    def __init__(self, sessions: sessionmaker[Session], storage: StorageService) -> None:
        self.sessions, self.storage = sessions, storage
        self.files = storage.local  # Compatibility accessor for existing internal local tests.

    def identity(self, video_id: str) -> tuple[str, str]:
        with self.sessions() as session:
            video = LibraryRepository(session).get_by_id(video_id)
            if video is None:
                raise NotFoundError("Video was not found")
            return video.platform.value, video.platform_video_id

    def begin_attempt(
        self, metadata: NormalizedVideo, payload: DownloadPayload, claim: Claim
    ) -> tuple[str, str | None]:
        with self.sessions.begin() as session:
            # First operation is a fenced write, avoiding SQLite read-to-write races.
            job = JobRepository(session).heartbeat(claim.id, claim.attempt, utc_now())
            if job is None or job.cancel_requested_at is not None:
                raise DownloadCancelledError()
            repository = LibraryRepository(session)
            video = repository.upsert(metadata)
            if not payload.force and repository.has_history(video.id):
                return video.id, None
            event = repository.start_attempt(video.id, claim, payload)
            ids = video.id, event.id
        logger.info("Video resolved and download attempt persisted")
        return ids

    @staticmethod
    def _history(row: Download) -> HistoryItem:
        return HistoryItem(
            **{
                name: getattr(row, name)
                for name in HistoryItem.model_fields
                if name not in {"title", "platform"}
            },
            title=row.video.title,
            platform=row.video.platform,
        )

    @staticmethod
    def _video(repository: LibraryRepository, video: Video, has_file: bool) -> LibraryVideo:
        return LibraryVideo(
            **{
                name: getattr(video, name)
                for name in LibraryVideo.model_fields
                if name
                not in {"creator", "has_file", "has_download_history", "tags", "collections"}
            },
            creator=(video.creator.name or video.creator.handle)
            if video.creator
            else video.metadata_json.get("creator_name"),
            has_file=has_file,
            has_download_history=repository.has_history(video.id),
            tags=[
                NamedItem(id=item.id, name=item.name) for item in repository.named(video.id, "tags")
            ],
            collections=[
                NamedItem(id=item.id, name=item.name)
                for item in repository.named(video.id, "collections")
            ],
        )

    def detail(self, video_id: str, *, verify_remote: bool = False) -> VideoDetail:
        self.identity(video_id)
        with self.sessions() as session:
            repository = LibraryRepository(session)
            video = repository.get_by_id(video_id)
            records = repository.files(video_id)
            summary = self._video(repository, video, False)
            description = video.description
            events, _ = repository.history(page=1, page_size=100, video_id=video_id)
            history = [self._history(event) for event in events]
        files: list[FileSummary] = []
        changes: list[tuple[str, bool]] = []
        for record in records:
            if record.deleted_at is not None:
                state = "deleted"
            else:
                state, present = self.storage.file_state(
                    record.storage_provider,
                    record.storage_key,
                    record.missing_at is not None,
                    verify_remote=verify_remote,
                )
                if present is not None and (record.missing_at is not None) == present:
                    changes.append((record.id, not present))
            files.append(
                FileSummary(
                    id=record.id,
                    storage_provider=record.storage_provider,
                    file_name=record.file_name.replace("\\", "/").rsplit("/", 1)[-1],
                    size_bytes=record.size_bytes,
                    sha256=record.sha256,
                    container=Path(record.file_name).suffix.lstrip("."),
                    width=record.width,
                    height=record.height,
                    state=state,
                )
            )
        if changes:
            with self.sessions.begin() as session:
                LibraryRepository(session).reconcile(changes)
        return VideoDetail(
            **{
                **summary.model_dump(),
                "has_file": any(f.state in {"available", "stored"} for f in files),
            },
            description=description,
            history=history,
            files=files[:100],
        )

    def list(self, **filters: object) -> VideoPage:
        with self.sessions() as session:
            rows, total = LibraryRepository(session).page(**filters)
            ids = [row.id for row in rows]
        items = [
            LibraryVideo(**self.detail(video_id).model_dump(include=set(LibraryVideo.model_fields)))
            for video_id in ids
        ]
        return VideoPage(
            items=items, total=total, page=filters["page"], page_size=filters["page_size"]
        )

    def history(self, **filters: object) -> HistoryPage:
        with self.sessions() as session:
            rows, total = LibraryRepository(session).history(**filters)
            return HistoryPage(
                items=[self._history(row) for row in rows],
                total=total,
                page=filters["page"],
                page_size=filters["page_size"],
            )

    def destroy(self, video_id: str, operation: str) -> VideoDetail:
        if operation not in {"file", "history", "all"}:
            raise ConflictError("Unknown library operation")
        with identity_lock(*self.identity(video_id)):
            if operation in {"file", "all"}:
                with self.sessions() as session:
                    records = LibraryRepository(session).files(video_id)
                active = [record for record in records if record.deleted_at is None]
                # Validate every target before deleting any. DB paths are untrusted.
                for record in active:
                    self.storage.validate_delete(record.storage_provider, record.storage_key)
                for record in active:
                    self.storage.delete(record.storage_provider, record.storage_key)
                    with self.sessions.begin() as session:
                        LibraryRepository(session).mark_deleted(record.id)
            if operation in {"history", "all"}:
                with self.sessions.begin() as session:
                    LibraryRepository(session).remove_history(video_id)
                logger.info("Download history removed")
            return self.detail(video_id)

    def source(self, video_id: str) -> str:
        with self.sessions() as session:
            video = LibraryRepository(session).get_by_id(video_id)
            if video is None:
                raise NotFoundError("Video was not found")
            try:
                return DownloadPayload(url=video.canonical_url, max_height=1080).url
            except Exception:
                raise ConflictError("Video has no safe source URL for redownload") from None

    def organization(self, kind: str, name: str | None = None) -> list[NamedItem] | NamedItem:
        with self.sessions.begin() as session:
            repository = OrganizationRepository(session)
            if name is not None:
                row = repository.create(kind, name)
                return NamedItem(id=row.id, name=row.name)
            return [NamedItem(id=row.id, name=row.name) for row in repository.list(kind)]

    def attach(
        self, kind: str, item_id: str, video_id: str, *, remove: bool = False
    ) -> VideoDetail:
        with self.sessions.begin() as session:
            if not LibraryRepository(session).reserve_video(video_id):
                raise NotFoundError("Video was not found")
            if not OrganizationRepository(session).attach(kind, item_id, video_id, remove=remove):
                raise NotFoundError("Organization item was not found")
        return self.detail(video_id)
