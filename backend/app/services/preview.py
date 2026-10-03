from app.repositories.library import LibraryRepository
from app.schemas.preview import VideoPreview
from app.services.downloader.service import DownloaderService
from app.services.library.service import LibraryService


class PreviewService:
    def __init__(self, downloader: DownloaderService, library: LibraryService) -> None:
        self.downloader = downloader
        self.library = library

    def resolve(self, url: str) -> VideoPreview:
        video = self.downloader.resolve(url)
        state = {}
        with self.library.sessions() as session:
            existing = LibraryRepository(session).get_by_platform_identity(
                video.platform, video.platform_video_id
            )
            video_id = existing.id if existing else None
        if video_id:
            detail = self.library.detail(video_id)
            state = {
                "video_id": video_id,
                "has_file": detail.has_file,
                "has_download_history": detail.has_download_history,
            }
        return VideoPreview(
            **{
                name: getattr(video, name)
                for name in VideoPreview.model_fields
                if name not in {"video_id", "has_file", "has_download_history"}
            },
            **state,
        )
