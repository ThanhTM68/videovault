from app.schemas.preview import VideoPreview
from app.services.downloader.service import DownloaderService


class PreviewService:
    def __init__(self, downloader: DownloaderService) -> None:
        self.downloader = downloader

    def resolve(self, url: str) -> VideoPreview:
        video = self.downloader.resolve(url)
        return VideoPreview(**{name: getattr(video, name) for name in VideoPreview.model_fields})
