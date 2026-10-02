from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MediaFile


class MediaFileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, media_id: str) -> MediaFile | None:
        return self.session.get(MediaFile, media_id)

    def list_for_video(self, video_id: str) -> list[MediaFile]:
        return list(
            self.session.scalars(
                select(MediaFile)
                .where(MediaFile.video_id == video_id)
                .order_by(MediaFile.created_at, MediaFile.id)
            )
        )

    def add(self, media: MediaFile) -> MediaFile:
        self.session.add(media)
        self.session.flush()
        return media

    def delete(self, media: MediaFile) -> None:
        """Remove a record only; never access or remove physical storage."""
        self.session.delete(media)
        self.session.flush()
