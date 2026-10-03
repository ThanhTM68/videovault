from collections.abc import Iterator
from contextlib import contextmanager
from threading import Event

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.models.enums import StorageProvider as Provider
from app.schemas.storage import ProviderStatus, StorageStatus
from app.services.downloader.service import DownloadResult
from app.services.storage.contracts import (
    ObjectMetadata,
    StorageProvider,
    StoredObject,
    UploadProgress,
)
from app.services.storage.drive import GoogleDriveStorageProvider
from app.services.storage.errors import StorageError
from app.services.storage.local import LocalStorageProvider
from app.services.storage.oauth import DriveConnection


class StorageService:
    def __init__(self, settings: Settings, sessions: sessionmaker[Session]) -> None:
        self.settings = settings
        self.local = LocalStorageProvider(settings.local_storage_root, settings.temp_storage_root)
        self.connection = DriveConnection(settings, sessions)
        self.drive = GoogleDriveStorageProvider(self.connection)
        self.providers: dict[Provider, StorageProvider] = {
            Provider.LOCAL: self.local,
            Provider.GOOGLE_DRIVE: self.drive,
        }

    def status(self) -> StorageStatus:
        return StorageStatus(
            default_target=self.settings.storage_provider,
            providers=[
                ProviderStatus(
                    provider=Provider.LOCAL, configured=True, connected=True, available=True
                ),
                self.connection.status(),
            ],
        )

    def check_available(self, target: Provider) -> None:
        self.providers[target].check_available()

    @contextmanager
    def operation(self, target: Provider, cancellation: Event) -> Iterator[None]:
        if self.providers[target].remote:
            with self.connection.lease(cancellation):
                yield
        else:
            yield

    def put(
        self,
        target: Provider,
        result: DownloadResult,
        cancellation: Event,
        progress: UploadProgress,
    ) -> StoredObject:
        self.local.source_path(result.path)
        provider = self.providers[target]
        if provider.remote:
            progress(0)
        return provider.put(result, cancellation, progress)

    def delete(self, target: Provider, key: str) -> None:
        self.providers[target].delete(key)

    def validate_delete(self, target: Provider, key: str) -> None:
        self.providers[target].validate_delete(key)

    def exists(self, target: Provider, key: str) -> bool:
        return self.providers[target].exists(key)

    def get_metadata(self, target: Provider, key: str) -> ObjectMetadata | None:
        return self.providers[target].get_metadata(key)

    def file_state(
        self, target: Provider, key: str, missing: bool, *, verify_remote: bool
    ) -> tuple[str, bool | None]:
        provider = self.providers[target]
        if provider.remote and not verify_remote:
            # A cached flag is explicitly last-known, never a remote existence claim.
            return ("missing" if missing else "stored"), None
        try:
            present = provider.exists(key)
        except StorageError:
            return "unavailable", None
        return ("available" if present else "missing"), present
