"""Compatibility imports; local lifecycle has one implementation in storage.local."""

from app.services.storage.contracts import StoredObject as FinalizedFile
from app.services.storage.local import CHUNK_SIZE
from app.services.storage.local import LocalStorageProvider as LocalFiles

__all__ = ["CHUNK_SIZE", "FinalizedFile", "LocalFiles"]
