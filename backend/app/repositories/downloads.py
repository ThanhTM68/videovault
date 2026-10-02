from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Download
from app.models.enums import DownloadStatus


class DownloadRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, download_id: str) -> Download | None:
        return self.session.get(Download, download_id)

    def add(self, download: Download) -> Download:
        self.session.add(download)
        self.session.flush()
        return download

    def list_successful_for_video(self, video_id: str) -> list[Download]:
        return list(
            self.session.scalars(
                select(Download)
                .where(Download.video_id == video_id, Download.status == DownloadStatus.COMPLETED)
                .order_by(Download.created_at, Download.id)
            )
        )

    def delete(self, download: Download) -> None:
        self.session.delete(download)
        self.session.flush()
