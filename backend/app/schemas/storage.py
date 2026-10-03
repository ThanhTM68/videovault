from pydantic import Field

from app.models.enums import StorageProvider
from app.services.downloader.models import DomainModel


class ProviderStatus(DomainModel):
    provider: StorageProvider
    configured: bool
    connected: bool
    available: bool
    display_name: str | None = None
    account_id: str | None = None
    root_folder_id: str | None = None
    error_code: str | None = None


class StorageStatus(DomainModel):
    default_target: StorageProvider
    providers: list[ProviderStatus]


class ConnectResult(DomainModel):
    authorization_url: str


class RootInput(DomainModel):
    folder_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9_-]+$")


class FolderResult(DomainModel):
    id: str
    name: str


class EmptyInput(DomainModel):
    pass
