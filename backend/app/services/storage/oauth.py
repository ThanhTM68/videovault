import json
import secrets
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from threading import Event, RLock

from google.auth.exceptions import RefreshError, TransportError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import Resource
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.models.enums import StorageProvider
from app.repositories.storage import StorageAccountRepository
from app.schemas.storage import ProviderStatus
from app.services.downloader.cancellation import DownloadCancelledError
from app.services.storage.credentials import CredentialFile
from app.services.storage.errors import StorageError
from app.services.storage.google_client import (
    SCOPES,
    RefreshRequest,
    build_client,
    call_google,
    folder_metadata,
)


class DriveConnection:
    def __init__(
        self,
        settings: Settings,
        sessions: sessionmaker[Session],
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings, self.sessions, self.clock = settings, sessions, clock
        self.tokens = CredentialFile(settings.private_auth_root)
        self.lock = RLock()
        self.states: dict[str, tuple[float, Flow]] = {}
        self.client_factory = build_client
        self.flow_factory = Flow.from_client_config

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.google_drive_client_id
            and self.settings.google_drive_client_secret.get_secret_value()
            and self.settings.google_drive_redirect_uri
        )

    def _credentials(self) -> Credentials:
        if not self.configured:
            raise StorageError("STORAGE_NOT_CONFIGURED")
        data = self.tokens.read()
        if not data or data.get("client_id") != self.settings.google_drive_client_id:
            raise StorageError("STORAGE_NOT_CONNECTED")
        try:
            credentials = Credentials.from_authorized_user_info(data, scopes=SCOPES)
        except (ValueError, TypeError, KeyError):
            raise StorageError("STORAGE_NOT_CONNECTED") from None
        return credentials

    def status(self) -> ProviderStatus:
        # Atomic credential reads and short DB snapshots never wait for uploads.
        with self.sessions() as session:
            row = StorageAccountRepository(session).get_drive()
            display = row.display_name if row else None
            identity = row.provider_account_id if row else None
            root = row.config_json.get("root_folder_id") if row else None
        code = None
        connected = False
        try:
            credentials = self._credentials()
            connected = bool(identity and (credentials.valid or credentials.refresh_token))
            if not connected:
                code = "STORAGE_NOT_CONNECTED"
        except StorageError as exc:
            code = exc.code
        return ProviderStatus(
            provider=StorageProvider.GOOGLE_DRIVE,
            configured=self.configured,
            connected=connected,
            available=bool(connected and root),
            display_name=display,
            account_id=identity,
            root_folder_id=root,
            error_code=code or (None if root else "STORAGE_ROOT_INVALID"),
        )

    @contextmanager
    def lease(self, cancellation: Event | None = None) -> Iterator[None]:
        while not self.lock.acquire(timeout=0.1):
            if cancellation and cancellation.is_set():
                raise DownloadCancelledError()
        try:
            if cancellation and cancellation.is_set():
                raise DownloadCancelledError()
            yield
        finally:
            self.lock.release()

    @contextmanager
    def client(self) -> Iterator[Resource]:
        with self.lock:
            credentials = self._credentials()
            client = None
            try:
                if not credentials.valid:
                    credentials.refresh(RefreshRequest())
                    self.tokens.write(json.loads(credentials.to_json()))
                client = self.client_factory(credentials)
                yield client
                # AuthorizedHttp can refresh again during a long upload.
                self.tokens.write(json.loads(credentials.to_json()))
            except RefreshError as exc:
                if getattr(exc, "retryable", False):
                    raise StorageError("STORAGE_UNAVAILABLE") from None
                self.tokens.delete()
                raise StorageError("STORAGE_NOT_CONNECTED") from None
            except TransportError:
                raise StorageError("STORAGE_UNAVAILABLE") from None
            except StorageError as exc:
                if exc.code == "STORAGE_NOT_CONNECTED":
                    self.tokens.delete()
                raise
            finally:
                if client is not None:
                    client.close()

    def start(self) -> str:
        with self.lock:
            if not self.configured:
                raise StorageError("STORAGE_NOT_CONFIGURED")
            self.states = {
                key: value for key, value in self.states.items() if value[0] > self.clock()
            }
            if len(self.states) >= 32:
                self.states.pop(next(iter(self.states)))
            state = secrets.token_urlsafe(32)
            try:
                flow = self.flow_factory(
                    {
                        "web": {
                            "client_id": self.settings.google_drive_client_id,
                            "client_secret": (
                                self.settings.google_drive_client_secret.get_secret_value()
                            ),
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token",
                        }
                    },
                    scopes=SCOPES,
                    redirect_uri=self.settings.google_drive_redirect_uri,
                    autogenerate_code_verifier=True,
                )
                url, _ = flow.authorization_url(
                    state=state, access_type="offline", prompt="consent"
                )
            except Exception:
                raise StorageError("OAUTH_FAILED") from None
            self.states[state] = (self.clock() + 600, flow)
            return url

    def callback(self, state: str, code: str | None, error: str | None) -> None:
        with self.lock:
            pending = self.states.pop(state, None)
            if pending is None or pending[0] <= self.clock():
                raise StorageError("OAUTH_STATE_INVALID")
            if error:
                raise StorageError("OAUTH_DENIED")
            if not code:
                raise StorageError("OAUTH_FAILED")
            client = None
            try:
                flow = pending[1]
                flow.fetch_token(code=code, timeout=30)
                credentials = flow.credentials
                if not credentials.refresh_token:
                    raise StorageError("OAUTH_FAILED")
                client = self.client_factory(credentials)
                user = call_google(
                    lambda: (
                        client.about()
                        .get(fields="user(displayName,permissionId)")
                        .execute(num_retries=0)
                    )
                )["user"]
                identity = user.get("permissionId")
                if not isinstance(identity, str) or not identity:
                    raise StorageError("OAUTH_FAILED")
                with self.sessions() as session:
                    old = StorageAccountRepository(session).get_drive()
                    if old and old.provider_account_id not in {None, identity}:
                        raise StorageError("STORAGE_ACCOUNT_MISMATCH")
                    root = old.config_json.get("root_folder_id") if old else None
                configured_root = self.settings.google_drive_root_folder_id
                if not root and configured_root:
                    root = str(folder_metadata(client, configured_root)["id"])
                previous = self.tokens.read()
                self.tokens.write(json.loads(credentials.to_json()))
                try:
                    with self.sessions.begin() as session:
                        repository = StorageAccountRepository(session)
                        repository.bind(identity, str(user.get("displayName") or "Google Drive"))
                        if root:
                            repository.root(root)
                except Exception:
                    if previous is None:
                        self.tokens.delete()
                    else:
                        self.tokens.write(previous)
                    raise
            except StorageError:
                raise
            except Exception:
                raise StorageError("OAUTH_FAILED") from None
            finally:
                if client is not None:
                    client.close()

    def disconnect(self) -> None:
        with self.lock:
            self.states.clear()
            self.tokens.delete()
