"""Import the complete V1 metadata without importing or starting the API application."""

from app.models.download import Download, MediaFile
from app.models.job import Job
from app.models.organization import Collection, CollectionVideo, Tag, VideoTag
from app.models.storage import StorageAccount
from app.models.video import Creator, Video

__all__ = [
    "Collection",
    "CollectionVideo",
    "Creator",
    "Download",
    "Job",
    "MediaFile",
    "StorageAccount",
    "Tag",
    "Video",
    "VideoTag",
]
