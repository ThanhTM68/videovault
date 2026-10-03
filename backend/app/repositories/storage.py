from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import StorageAccount
from app.models.enums import StorageProvider
from app.services.storage.errors import StorageError


class StorageAccountRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_drive(self) -> StorageAccount | None:
        rows = list(
            self.session.scalars(
                select(StorageAccount)
                .where(StorageAccount.provider == StorageProvider.GOOGLE_DRIVE)
                .limit(2)
            )
        )
        if len(rows) > 1:
            raise StorageError("STORAGE_ACCOUNT_AMBIGUOUS")
        return rows[0] if rows else None

    def bind(self, identity: str, name: str) -> StorageAccount:
        self._reserve_drive()
        row = self.get_drive()
        if row and row.provider_account_id not in {None, identity}:
            raise StorageError("STORAGE_ACCOUNT_MISMATCH")
        if row is None:
            row = StorageAccount(provider=StorageProvider.GOOGLE_DRIVE, display_name=name)
            self.session.add(row)
        row.provider_account_id = identity
        row.display_name = name
        self.session.flush()
        return row

    def root(self, folder_id: str) -> None:
        self._reserve_drive()
        row = self.get_drive()
        if row is None:
            raise StorageError("STORAGE_NOT_CONNECTED")
        row.config_json = {**row.config_json, "root_folder_id": folder_id}

    def _reserve_drive(self) -> None:
        # Even an empty UPDATE reserves SQLite's writer. A SELECT first could
        # deadlock its later write upgrade against a worker claiming a job.
        self.session.execute(
            update(StorageAccount)
            .where(StorageAccount.provider == StorageProvider.GOOGLE_DRIVE)
            .values(display_name=StorageAccount.display_name)
        )
