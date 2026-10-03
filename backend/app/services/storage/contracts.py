from collections.abc import Callable
from dataclasses import dataclass
from threading import Event
from typing import Protocol

from app.models.enums import StorageProvider as Provider
from app.services.downloader.service import DownloadResult

UploadProgress = Callable[[float], None]


@dataclass(frozen=True)
class StoredObject:
    key: str
    sha256: str
    size: int
    provider: Provider
    file_name: str
    mime_type: str


@dataclass(frozen=True)
class ObjectMetadata:
    key: str
    file_name: str
    size: int | None
    mime_type: str


class StorageProvider(Protocol):
    remote: bool

    def check_available(self) -> None: ...
    def validate_delete(self, key: str) -> None: ...
    def put(
        self, result: DownloadResult, cancellation: Event, progress: UploadProgress
    ) -> StoredObject: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def get_metadata(self, key: str) -> ObjectMetadata | None: ...
