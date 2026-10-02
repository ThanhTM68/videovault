from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    """Store naive UTC in SQLite; require and return aware application datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamps must be timezone-aware")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


class StorageConfig(TypeDecorator[dict[str, str]]):
    """Small non-secret configuration shell; never store tokens or credentials."""

    impl = JSON
    cache_ok = True

    def process_bind_param(self, value: dict[str, str] | None, dialect: Dialect) -> dict[str, str]:
        if not isinstance(value, dict) or not set(value) <= {"root_path", "root_folder_id"}:
            raise ValueError("Storage config supports only root_path and root_folder_id")
        if not all(isinstance(item, str) for item in value.values()):
            raise ValueError("Storage config values must be strings")
        return value
