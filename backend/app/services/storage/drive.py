import hashlib
import logging
from datetime import UTC, datetime
from threading import Event
from uuid import uuid4

from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from app.models.enums import StorageProvider
from app.repositories.storage import StorageAccountRepository
from app.schemas.storage import FolderResult
from app.services.downloader.cancellation import DownloadCancelledError
from app.services.downloader.paths import safe_component, video_filename
from app.services.downloader.service import DownloadResult
from app.services.storage.contracts import ObjectMetadata, StoredObject, UploadProgress
from app.services.storage.errors import StorageError
from app.services.storage.google_client import FOLDER_MIME, call_google, drive_id, folder_metadata
from app.services.storage.local import CHUNK_SIZE, MIME_TYPES
from app.services.storage.oauth import DriveConnection

logger = logging.getLogger(__name__)
MEDIA_MARKER = {"videovault_kind": "media"}


def quote_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


class GoogleDriveStorageProvider:
    remote = True

    def __init__(self, connection: DriveConnection) -> None:
        self.connection = connection

    def _connected(self) -> None:
        status = self.connection.status()
        if not status.configured:
            raise StorageError("STORAGE_NOT_CONFIGURED")
        if not status.connected:
            raise StorageError(status.error_code or "STORAGE_NOT_CONNECTED")

    def check_available(self) -> None:
        self._connected()
        if not self.connection.status().root_folder_id:
            raise StorageError("STORAGE_ROOT_INVALID")

    def _folder(self, client: Resource, parent: str, name: str, signal: Event) -> str:
        query = (
            f"'{quote_query(drive_id(parent))}' in parents and "
            f"mimeType = '{FOLDER_MIME}' and trashed = false and "
            f"name = '{quote_query(name)}'"
        )
        # Deterministic oldest folder, then smallest ID within the bounded first page.
        items = call_google(
            lambda: (
                client.files()
                .list(
                    q=query,
                    fields="files(id,name,createdTime)",
                    pageSize=100,
                    orderBy="createdTime,name",
                    spaces="drive",
                )
                .execute(num_retries=0)
            ),
            cancellation=signal,
        ).get("files", [])
        if items:
            return drive_id(
                sorted(items, key=lambda item: (item.get("createdTime", ""), item["id"]))[0]["id"]
            )
        item = call_google(
            lambda: (
                client.files()
                .create(
                    body={
                        "name": name,
                        "mimeType": FOLDER_MIME,
                        "parents": [parent],
                        "appProperties": {"videovault_kind": "folder"},
                    },
                    fields="id",
                )
                .execute(num_retries=0)
            ),
            cancellation=signal,
            retry=False,
        )
        return drive_id(item["id"])

    def set_root(self, folder_id: str | None = None) -> FolderResult:
        with self.connection.lease():
            self._connected()
            with self.connection.client() as client:
                if folder_id is None:
                    folder_id = self._folder(client, "root", "VideoVault", Event())
                metadata = folder_metadata(client, folder_id)
            with self.connection.sessions.begin() as session:
                StorageAccountRepository(session).root(str(metadata["id"]))
            return FolderResult(id=str(metadata["id"]), name=str(metadata["name"]))

    def _metadata(self, client: Resource, key: str) -> dict[str, object] | None:
        try:
            item = call_google(
                lambda: (
                    client.files()
                    .get(fileId=drive_id(key), fields="id,name,size,mimeType,trashed,appProperties")
                    .execute(num_retries=0)
                )
            )
        except HttpError as exc:
            if exc.resp.status == 404:
                return None
            raise StorageError() from None
        if item.get("trashed"):
            return None
        if (
            item.get("appProperties", {}).get("videovault_kind") != "media"
            or item.get("mimeType") == FOLDER_MIME
        ):
            raise StorageError("STORAGE_UNMANAGED_OBJECT")
        return item

    def validate_delete(self, key: str) -> None:
        # Syntax/config validation before mixed-provider deletion starts; remote
        # ownership is verified again immediately before the actual delete.
        drive_id(key)
        self._connected()

    def get_metadata(self, key: str) -> ObjectMetadata | None:
        self._connected()
        with self.connection.client() as client:
            item = self._metadata(client, key)
            if item is None:
                return None
            return ObjectMetadata(
                key,
                str(item["name"]),
                int(item["size"]) if "size" in item else None,
                str(item["mimeType"]),
            )

    def exists(self, key: str) -> bool:
        return self.get_metadata(key) is not None

    def delete(self, key: str) -> None:
        self.validate_delete(key)
        with self.connection.client() as client:
            if self._metadata(client, key) is None:
                return
            try:
                call_google(
                    lambda: client.files().delete(fileId=key).execute(num_retries=0),
                    error_code="STORAGE_DELETE_FAILED",
                )
            except HttpError as exc:
                if exc.resp.status != 404:
                    raise StorageError("STORAGE_DELETE_FAILED") from None

    def put(
        self, result: DownloadResult, cancellation: Event, progress: UploadProgress
    ) -> StoredObject:
        self.check_available()
        owned_id = None
        media = None
        try:
            digest = hashlib.sha256()
            with result.path.open("rb") as source:
                while chunk := source.read(CHUNK_SIZE):
                    if cancellation.is_set():
                        raise DownloadCancelledError()
                    digest.update(chunk)
            with self.connection.client() as client:
                root = self.connection.status().root_folder_id
                folder_metadata(client, root)
                video = result.video
                date = video.upload_date or datetime.now(UTC).date()
                creator = (
                    f"{safe_component(video.creator, 32)}_"
                    f"{safe_component(video.creator_id or 'unknown', 24)}"
                )
                parent = root
                for name in (video.platform.value, creator, str(date.year), f"{date.month:02}"):
                    parent = self._folder(client, parent, safe_component(name), cancellation)
                file_name = f"{video_filename(video)}_{uuid4().hex}{result.path.suffix.lower()}"
                mime = MIME_TYPES[result.path.suffix.lower()]
                # A fresh pre-generated ID makes even lost final responses compensatable.
                owned_id = drive_id(
                    call_google(
                        lambda: (
                            client.files()
                            .generateIds(count=1, space="drive", type="files")
                            .execute(num_retries=0)
                        ),
                        cancellation=cancellation,
                    )["ids"][0]
                )
                media = MediaFileUpload(
                    str(result.path), mimetype=mime, chunksize=CHUNK_SIZE, resumable=True
                )
                upload = client.files().create(
                    body={
                        "id": owned_id,
                        "name": file_name,
                        "parents": [parent],
                        "appProperties": MEDIA_MARKER,
                    },
                    media_body=media,
                    fields="id,size",
                )
                response = None
                while response is None:
                    status, response = call_google(
                        lambda: upload.next_chunk(num_retries=0),
                        cancellation=cancellation,
                        error_code="STORAGE_UPLOAD_FAILED",
                    )
                    if status is not None:
                        progress(min(float(status.progress()) * 100, 99))
                if (
                    response.get("id") != owned_id
                    or int(response.get("size", -1)) != result.probe.size_bytes
                ):
                    raise StorageError("STORAGE_UPLOAD_FAILED")
                if cancellation.is_set():
                    raise DownloadCancelledError()
                return StoredObject(
                    owned_id,
                    digest.hexdigest(),
                    result.probe.size_bytes,
                    StorageProvider.GOOGLE_DRIVE,
                    file_name,
                    mime,
                )
        except Exception as exc:
            if owned_id:
                try:
                    self.delete(owned_id)
                except Exception:
                    logger.warning("Drive orphan possible: upload compensation failed")
            if isinstance(exc, (StorageError, DownloadCancelledError)):
                raise
            raise StorageError("STORAGE_UPLOAD_FAILED") from None
        finally:
            if media is not None:
                media.stream().close()
