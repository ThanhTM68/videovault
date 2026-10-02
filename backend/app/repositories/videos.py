from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Video
from app.models.enums import Platform


class VideoRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, video_id: str) -> Video | None:
        return self.session.get(Video, video_id)

    def get_by_platform_identity(self, platform: Platform, platform_video_id: str) -> Video | None:
        return self.session.scalar(
            select(Video).where(
                Video.platform == platform, Video.platform_video_id == platform_video_id
            )
        )

    def add(self, video: Video) -> Video:
        self.session.add(video)
        self.session.flush()
        return video

    def delete(self, video: Video) -> None:
        self.session.delete(video)
        self.session.flush()
