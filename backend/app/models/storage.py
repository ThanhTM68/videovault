from sqlalchemy import Text
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedMixin, IdentityMixin
from app.db.types import StorageConfig
from app.models.enums import StorageProvider, enum_column


class StorageAccount(IdentityMixin, CreatedMixin, Base):
    __tablename__ = "storage_accounts"
    provider: Mapped[StorageProvider] = mapped_column(
        enum_column(StorageProvider, "storage_provider")
    )
    display_name: Mapped[str] = mapped_column(Text)
    provider_account_id: Mapped[str | None] = mapped_column(Text)
    config_json: Mapped[dict[str, str]] = mapped_column(
        MutableDict.as_mutable(StorageConfig()), default=dict
    )
