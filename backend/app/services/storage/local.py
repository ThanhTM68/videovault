import hashlib
import logging
import os
import stat
from pathlib import Path, PureWindowsPath
from threading import Event
from uuid import uuid4

from app.models.enums import StorageProvider
from app.services.downloader.cancellation import DownloadCancelledError
from app.services.downloader.paths import video_filename
from app.services.downloader.service import DownloadResult
from app.services.library.errors import LibraryFileError
from app.services.storage.contracts import ObjectMetadata, StoredObject, UploadProgress

logger = logging.getLogger(__name__)
CHUNK_SIZE = 1024 * 1024


MIME_TYPES = {".mp4": "video/mp4", ".mkv": "video/x-matroska", ".webm": "video/webm"}


class LocalStorageProvider:
    remote = False

    def __init__(self, root: Path, temp_root: Path) -> None:
        self.root = root.absolute()
        self.temp_root = temp_root.absolute()

    def check_available(self) -> None:
        # Roots are created lazily by put; actual permissions are checked on I/O.
        pass

    def validate_delete(self, key: str) -> None:
        self.path(key)

    def put(
        self, result: DownloadResult, cancellation: Event, progress: UploadProgress
    ) -> StoredObject:
        return self.finalize(result, cancellation)

    def get_metadata(self, key: str) -> ObjectMetadata | None:
        if not self.exists(key):
            return None
        try:
            path = self.path(key)
            return ObjectMetadata(key, path.name, path.stat().st_size, MIME_TYPES[path.suffix])
        except (OSError, KeyError):
            raise LibraryFileError() from None

    def source_path(self, path: Path) -> Path:
        return self._checked(self.temp_root, path)

    @staticmethod
    def _checked(root: Path, target: Path) -> Path:
        resolved_root = root.resolve()
        resolved = target.resolve()
        if resolved == resolved_root or not resolved.is_relative_to(resolved_root):
            raise LibraryFileError("FILE_OUTSIDE_MANAGED_ROOT")
        # Reject links/reparse points along the entire lexical chain, including root.
        for component in [target, *target.parents]:
            try:
                info = component.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise LibraryFileError("FILE_OUTSIDE_MANAGED_ROOT")
        return resolved

    def path(self, key: str) -> Path:
        # Storage keys are relative POSIX-style names, not arbitrary DB paths.
        win = PureWindowsPath(key)
        if not key or win.drive or win.is_absolute() or "\\" in key or ":" in key:
            raise LibraryFileError("FILE_OUTSIDE_MANAGED_ROOT")
        relative = Path(key)
        if relative.is_absolute() or ".." in relative.parts:
            raise LibraryFileError("FILE_OUTSIDE_MANAGED_ROOT")
        return self._checked(self.root, self.root / relative)

    def exists(self, key: str) -> bool:
        try:
            return self.path(key).is_file()
        except OSError:
            raise LibraryFileError() from None

    def delete(self, key: str) -> None:
        try:
            self.path(key).unlink(missing_ok=True)
        except OSError:
            raise LibraryFileError("FILE_DELETE_FAILED") from None
        logger.info("Managed file deleted")

    def hash_file(self, key: str, cancellation: Event | None = None) -> str:
        try:
            digest = hashlib.sha256()
            with self.path(key).open("rb") as source:
                while chunk := source.read(CHUNK_SIZE):
                    if cancellation and cancellation.is_set():
                        raise DownloadCancelledError()
                    digest.update(chunk)
            return digest.hexdigest()
        except OSError:
            raise LibraryFileError("FILE_HASH_FAILED") from None

    def finalize(self, result: DownloadResult, cancellation: Event) -> StoredObject:
        key = f"{video_filename(result.video)}_{uuid4().hex}{result.path.suffix.lower()}"
        owned = False
        try:
            source = self._checked(self.temp_root, result.path)
            if not source.is_file():
                raise LibraryFileError()
            destination = self.path(key)
            self.root.mkdir(parents=True, exist_ok=True)
            # Exclusive creation never overwrites another event's output.
            with source.open("rb") as stream, destination.open("xb") as output:
                owned = True
                while chunk := stream.read(CHUNK_SIZE):
                    if cancellation.is_set():
                        raise DownloadCancelledError()
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            digest = self.hash_file(key, cancellation)
            size = destination.stat().st_size
            if size != result.probe.size_bytes:
                raise LibraryFileError()
            logger.info("Managed file finalized and hash calculated")
            return StoredObject(
                key,
                digest,
                size,
                StorageProvider.LOCAL,
                key,
                MIME_TYPES[result.path.suffix.lower()],
            )
        except Exception as exc:
            if owned:
                try:
                    self.delete(key)
                except LibraryFileError:
                    logger.warning("Owned file cleanup failed")
            if isinstance(exc, OSError):
                raise LibraryFileError() from None
            raise
