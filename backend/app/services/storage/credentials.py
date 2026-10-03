import json
import os
import stat
from pathlib import Path
from uuid import uuid4

from app.services.storage.errors import StorageError


class CredentialFile:
    """Private runtime state; fixed filename, atomic replace, never an API resource."""

    def __init__(self, root: Path) -> None:
        self.root = root.absolute()
        self.path = self.root / "google-drive.json"

    def _check(self, path: Path) -> None:
        for item in [path, *path.parents]:
            try:
                info = item.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise StorageError("STORAGE_CREDENTIAL_FAILED")

    def read(self) -> dict[str, object] | None:
        try:
            self._check(self.path)
            if not self.path.exists():
                return None
            if self.path.stat().st_size > 65536:
                raise ValueError()
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except (OSError, ValueError):
            raise StorageError("STORAGE_CREDENTIAL_FAILED") from None

    def write(self, data: dict[str, object]) -> None:
        temporary = self.root / (uuid4().hex + ".tmp")
        try:
            self._check(self.path)
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(self.root, 0o700)
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(data, output)
                output.flush()
                os.fsync(output.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        except (OSError, ValueError, TypeError):
            raise StorageError("STORAGE_CREDENTIAL_FAILED") from None
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                raise StorageError("STORAGE_CREDENTIAL_FAILED") from None

    def delete(self) -> None:
        try:
            self._check(self.path)
            self.path.unlink(missing_ok=True)
        except OSError:
            raise StorageError("STORAGE_CREDENTIAL_FAILED") from None
