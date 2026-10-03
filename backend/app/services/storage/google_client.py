import json
import re
from collections.abc import Callable
from threading import Event

import httplib2
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError

from app.services.downloader.cancellation import DownloadCancelledError
from app.services.storage.errors import StorageError

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
FOLDER_MIME = "application/vnd.google-apps.folder"


def drive_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", value):
        raise StorageError("STORAGE_KEY_INVALID")
    return value


class RefreshRequest(Request):
    def __call__(self, *args: object, **kwargs: object) -> object:
        kwargs["timeout"] = 30
        return super().__call__(*args, **kwargs)


def build_client(credentials: Credentials) -> Resource:
    transport = AuthorizedHttp(credentials, http=httplib2.Http(timeout=30), max_refresh_attempts=1)
    return build("drive", "v3", http=transport, cache_discovery=False, static_discovery=True)


def transient(exc: Exception) -> bool:
    if isinstance(exc, HttpError):
        if exc.resp.status in {408, 429, 500, 502, 503, 504}:
            return True
        if exc.resp.status == 403:
            try:
                reasons = json.loads(exc.content).get("error", {}).get("errors", [])
                return any(
                    item.get("reason")
                    in {"rateLimitExceeded", "userRateLimitExceeded", "backendError"}
                    for item in reasons
                )
            except (ValueError, AttributeError, TypeError):
                return False
        return False
    return isinstance(exc, (OSError, TimeoutError, httplib2.HttpLib2Error))


def call_google[T](
    action: Callable[[], T],
    *,
    cancellation: Event | None = None,
    error_code: str = "STORAGE_UNAVAILABLE",
    retry: bool = True,
) -> T:
    signal = cancellation or Event()
    for attempt in range(4 if retry else 1):
        if signal.is_set():
            raise DownloadCancelledError()
        try:
            return action()
        except HttpError as exc:
            if exc.resp.status == 404:
                raise
            if exc.resp.status == 401:
                raise StorageError("STORAGE_NOT_CONNECTED") from None
            if not transient(exc):
                raise StorageError(
                    "STORAGE_PERMISSION_DENIED" if exc.resp.status == 403 else error_code
                ) from None
        except (OSError, httplib2.HttpLib2Error):
            pass
        if not retry or attempt == 3:
            raise StorageError(error_code) from None
        if signal.wait(min(2**attempt, 4)):
            raise DownloadCancelledError()
    raise StorageError(error_code)


def folder_metadata(client: Resource, folder_id: str) -> dict[str, object]:
    try:
        item = call_google(
            lambda: (
                client.files()
                .get(
                    fileId=drive_id(folder_id),
                    fields="id,name,mimeType,trashed,capabilities(canAddChildren)",
                )
                .execute(num_retries=0)
            )
        )
    except HttpError:
        raise StorageError("STORAGE_ROOT_INVALID") from None
    if (
        item.get("trashed")
        or item.get("mimeType") != FOLDER_MIME
        or not item.get("capabilities", {}).get("canAddChildren")
    ):
        raise StorageError("STORAGE_ROOT_INVALID")
    return item
