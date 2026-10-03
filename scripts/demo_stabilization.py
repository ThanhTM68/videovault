"""Offline external adapters for a real VideoVault API/browser demo.

Run from the checkout with its installed backend: python scripts/demo_stabilization.py.
Only the explicitly marked demo root is used. Nothing is deleted on startup/restart.
This is a development runner, not a production endpoint or platform implementation.
Fake Drive faults: place {"delete": 403} or {"upload": 403} in the marked root's
fake-drive-fault.json. Known SDK operations accept 403/500; faults remain active
until the file is removed. Malformed or oversized fault files fail safely.
"""

from __future__ import annotations

import argparse
import json
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from threading import Event, Lock, RLock, Thread
from typing import Protocol
from urllib.parse import urlencode

CHECKOUT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CHECKOUT / "backend"))

import uvicorn  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from google.oauth2.credentials import Credentials  # noqa: E402
from pydantic import SecretStr  # noqa: E402
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource  # noqa: E402

from app.application import create_app  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.models.enums import Platform  # noqa: E402
from app.repositories.storage import StorageAccountRepository  # noqa: E402
from app.services.downloader.adapters.youtube import YoutubeAdapter  # noqa: E402
from app.services.downloader.base import ProgressCallback  # noqa: E402
from app.services.downloader.cancellation import check_cancelled  # noqa: E402
from app.services.downloader.errors import DownloadFailedError, MetadataResolveError  # noqa: E402
from app.services.downloader.models import (  # noqa: E402
    DownloadRequest,
    NormalizedVideo,
    ProgressEvent,
    ProgressPhase,
)
from app.services.downloader.service import DownloaderService  # noqa: E402
from app.services.media.probe import require_tool  # noqa: E402
from app.services.queue.models import DownloadPayload  # noqa: E402
from app.services.sources.adapters import SourceAdapterRegistry, YouTubeSourceAdapter  # noqa: E402
from app.services.sources.service import SourceService  # noqa: E402
from app.services.storage.credentials import CredentialFile  # noqa: E402
from app.services.storage.errors import StorageError  # noqa: E402
from app.workers.download_worker import execute_download  # noqa: E402
from tests.downloader_fixtures import FIXTURES  # noqa: E402
from tests.source_fixtures import CHANNEL, entry  # noqa: E402
from tests.storage_fixtures import FakeDrive, FakeFlow, credentials, http_error  # noqa: E402

MARKER = ".videovault-demo.json"
MARKER_CONTENT = {"kind": "videovault-stabilization-demo", "version": 1}
SOURCE = "https://www.youtube.com/@demo/videos"
NORMAL_ID = "demo0000001"
SLOW_ID = "demoslow001"
FAIL_ID = "demofail001"
LONG_ID = "demolong001"
FAKE_CREDENTIAL_FIELDS = {
    "token": "test-access-token",
    "refresh_token": "test-refresh-token",
    "client_id": "test-client",
    "client_secret": "test-client-secret",
    "token_uri": "https://oauth2.googleapis.com/token",
}
FAULT_OPERATIONS = {"get", "about", "list", "create-folder", "generate-id", "upload", "delete"}


class DemoSettings(Settings):
    """Explicit demo inputs and defaults; ordinary project environment is ignored."""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)


def known_demo_credentials(data: dict[str, object]) -> bool:
    return all(data.get(key) == value for key, value in FAKE_CREDENTIAL_FIELDS.items())


def reject_demo_links(path: Path) -> None:
    """A marked demo must not redirect SQLite or generated media into other data."""
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            raise ValueError("Demo paths could not be safely inspected") from None
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Demo paths must not contain symlinks or reparse points")


def prepare_root(root: Path) -> Path:
    """Require an empty directory or our exact marker; never reset existing data."""
    root = root.expanduser().absolute()
    reject_demo_links(root)
    root = root.resolve()
    if root == Path(root.anchor) or root == Path.home().resolve():
        raise ValueError("Choose a separate demo directory")
    if root.exists() and not root.is_dir():
        raise ValueError("Demo root must be a directory")
    for name in (
        MARKER,
        "demo.db",
        "demo.db-journal",
        "demo.db-wal",
        "demo.db-shm",
        "fixtures",
        "downloads",
        "temp",
        "thumbnails",
        "private-auth",
        "fake-drive.json",
        "fake-drive.tmp",
        "fake-drive-fault.json",
        "fake-drive-media",
    ):
        reject_demo_links(root / name)
    if root.exists() and any(root.iterdir()):
        try:
            marker = json.loads((root / MARKER).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ValueError("Refusing a nonempty directory without the demo marker") from None
        if marker != MARKER_CONTENT:
            raise ValueError("Refusing a directory with a different demo marker")
    root.mkdir(parents=True, exist_ok=True)
    marker_path = root / MARKER
    if not marker_path.exists():
        with marker_path.open("x", encoding="utf-8") as marker_file:
            json.dump(MARKER_CONTENT, marker_file)
    return root


def fixture_url(identity: str) -> str:
    return "https://www.youtube.com/watch?v=" + identity


class DemoAdapter(YoutubeAdapter):
    """Synthetic metadata plus real generated media, cancellation and progress."""

    def __init__(self, root: Path, *, normal_seconds: float = 2, slow_seconds: float = 15):
        super().__init__()
        self.root, self.normal_seconds, self.slow_seconds = root, normal_seconds, slow_seconds
        self.lock = Lock()
        self.seed_mode = False
        self.transfers = 0

    def resolve(self, url: str) -> NormalizedVideo:
        identity = self._reference(url)
        if identity not in {SLOW_ID, FAIL_ID, LONG_ID} and (
            identity is None
            or len(identity) != 11
            or not identity.startswith("demo")
            or not identity[4:].isdigit()
            or not 1 <= int(identity[4:]) <= 100
        ):
            raise MetadataResolveError()
        title = "Demo video " + identity
        if identity == LONG_ID:
            title = "Long demo title " + "research video " * 30
        return self.normalize(
            FIXTURES["combined"]
            | {
                "id": identity,
                "extractor_key": "Youtube",
                "webpage_url": fixture_url(identity),
                "title": title,
                "channel": "Deterministic researcher",
                "channel_id": CHANNEL,
                "channel_url": SOURCE,
                "thumbnail": None,
                "formats": [
                    *FIXTURES["combined"]["formats"],
                    FIXTURES["combined"]["formats"][0] | {"format_id": "silent", "acodec": "none"},
                ],
            },
            url,
        )

    def media(self, container: str, audio: bool) -> Path:
        with self.lock:
            directory = self.root / "fixtures"
            directory.mkdir(exist_ok=True)
            path = directory / f"sample-{'audio' if audio else 'silent'}.{container}"
            if not path.exists():
                args = [
                    require_tool("ffmpeg"),
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=blue:s=64x48:r=10",
                ]
                if audio:
                    args += ["-f", "lavfi", "-i", "sine=frequency=400:sample_rate=44100"]
                args += [
                    "-t",
                    "0.3",
                    "-c:v",
                    "libvpx-vp9" if container == "webm" else "mpeg4",
                ]
                args += ["-c:a", "libopus" if container == "webm" else "aac"] if audio else ["-an"]
                args += ["-threads", "1", "-y", str(path)]
                subprocess.run(args, check=True, capture_output=True, timeout=30, shell=False)
            return path

    def download(
        self,
        video: NormalizedVideo,
        request: DownloadRequest,
        output_stem: Path,
        progress: ProgressCallback,
    ) -> Path:
        partial = output_stem.with_suffix(".part")
        partial.write_bytes(b"deterministic incomplete media")
        with self.lock:
            self.transfers += 1
        seconds = (
            0
            if self.seed_mode
            else (self.slow_seconds if video.platform_video_id == SLOW_ID else self.normal_seconds)
        )
        started = time.monotonic()
        while time.monotonic() - started < seconds:
            check_cancelled()
            progress(
                ProgressEvent(
                    phase=ProgressPhase.DOWNLOADING,
                    percent=min(95, 95 * (time.monotonic() - started) / seconds),
                )
            )
            Event().wait(0.05)
        check_cancelled()
        if video.platform_video_id == FAIL_ID:
            with self.lock:
                marker = self.root / "fail-once-consumed"
                if not marker.exists():
                    marker.write_text("A deliberate demo transfer failed once.\n", encoding="utf-8")
                    raise DownloadFailedError()
        progress(ProgressEvent(phase=ProgressPhase.PROCESSING))
        output = output_stem.with_suffix("." + request.preferred_container)
        shutil.copyfile(self.media(request.preferred_container, request.audio_enabled), output)
        partial.unlink()
        return output


class DemoSourceCore:
    def __init__(self, *, delay_seconds: float = 0):
        self.delay_seconds = delay_seconds

    def list_channel(self, url: str) -> dict[str, object]:
        if self.delay_seconds:
            Event().wait(self.delay_seconds)
        items = [entry(f"demo{i:07d}", i * 10, title=f"Demo candidate {i}") for i in range(1, 41)]
        items[2] = entry("demo0000003", None, view_count=None, upload_date=None)
        return deepcopy(
            {
                "_type": "playlist",
                "extractor_key": "YoutubeTab",
                "id": CHANNEL,
                "channel_id": CHANNEL,
                "channel": "Deterministic demo channel",
                "webpage_url": url,
                "entries": [*items, items[0]],
            }
        )


class Executable(Protocol):
    def execute(self, **kwargs: object) -> object: ...


class PersistentRequest:
    def __init__(self, drive: PersistentDrive, request: Executable):
        self.drive, self.request = drive, request

    def execute(self, **kwargs: object) -> object:
        with self.drive.lock:
            result = self.request.execute(**kwargs)
            self.drive.save()
            return result


class PersistentUpload:
    def __init__(self, drive: PersistentDrive, upload: object):
        self.drive, self.upload = drive, upload

    def next_chunk(self, **kwargs: object) -> tuple[object, object]:
        with self.drive.lock:
            status, result = self.upload.next_chunk(**kwargs)
            if result is not None:
                self.drive.media_root.mkdir(exist_ok=True)
                (self.drive.media_root / (result["id"] + ".bin")).write_bytes(
                    self.drive.uploaded_bytes
                )
                self.drive.save()
            return status, result


class PersistentDrive(FakeDrive):
    """Offline SDK boundary retaining actual fixture bytes across runner restarts."""

    def __init__(self, root: Path):
        super().__init__()
        self.lock = RLock()
        self.ledger = root / "fake-drive.json"
        self.fault = root / "fake-drive-fault.json"
        self.media_root = root / "fake-drive-media"
        if self.ledger.exists():
            data = json.loads(self.ledger.read_text(encoding="utf-8"))
            self.objects, self.serial = data["objects"], data["serial"]

    def network(self, operation: str) -> None:
        super().network(operation)
        try:
            reject_demo_links(self.fault)
            if not self.fault.exists():
                return
            with self.fault.open("rb") as source:
                payload = source.read(1025)
            if len(payload) > 1024:
                raise ValueError()
            faults = json.loads(payload)
            if not isinstance(faults, dict) or any(
                key not in FAULT_OPERATIONS or type(status) is not int or status not in {403, 500}
                for key, status in faults.items()
            ):
                raise ValueError()
        except (OSError, ValueError):
            raise StorageError("STORAGE_UNAVAILABLE") from None
        if operation in faults:
            raise http_error(faults[operation])

    def save(self) -> None:
        temporary = self.ledger.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"objects": self.objects, "serial": self.serial}), encoding="utf-8"
        )
        temporary.replace(self.ledger)

    def get(self, **kwargs: object) -> PersistentRequest:
        return PersistentRequest(self, super().get(**kwargs))

    def list(self, **kwargs: object) -> PersistentRequest:
        return PersistentRequest(self, super().list(**kwargs))

    def create(self, **kwargs: object) -> PersistentRequest | PersistentUpload:
        request = super().create(**kwargs)
        return (
            PersistentUpload(self, request)
            if kwargs.get("media_body") is not None
            else PersistentRequest(self, request)
        )

    def generateIds(self, **kwargs: object) -> PersistentRequest:
        return PersistentRequest(self, super().generateIds(**kwargs))

    def delete(self, fileId: str, **kwargs: object) -> PersistentRequest:
        request = super().delete(fileId=fileId, **kwargs)

        class DeleteRequest:
            def execute(inner_self, **options: object) -> object:
                result = request.execute(**options)
                (self.media_root / (fileId + ".bin")).unlink(missing_ok=True)
                return result

        return PersistentRequest(self, DeleteRequest())


def build_demo(
    root: Path,
    *,
    port: int = 8000,
    fake_drive: bool = False,
    connect_fake_drive: bool = False,
    source_delay: float = 0,
    seed_library: int = 0,
    preview_ttl: float = 600,
) -> FastAPI:
    root = prepare_root(root)
    existing_tokens = CredentialFile(root / "private-auth").read()
    if existing_tokens is not None and not known_demo_credentials(existing_tokens):
        raise ValueError("Refusing credentials that are not the known demo fixture")
    existing_database = (root / "demo.db").exists()
    require_tool("ffprobe")
    adapter = DemoAdapter(root)
    adapter.media("mp4", True)
    settings = DemoSettings(
        _env_file=None,
        app_env="test",
        app_port=port,
        database_url="sqlite:///" + (root / "demo.db").as_posix(),
        local_storage_root=root / "downloads",
        temp_storage_root=root / "temp",
        thumbnail_storage_root=root / "thumbnails",
        private_auth_root=root / "private-auth",
        google_drive_client_id="test-client" if fake_drive else "",
        google_drive_client_secret=SecretStr("test-client-secret" if fake_drive else ""),
        google_drive_redirect_uri=(
            f"http://127.0.0.1:{port}/api/v1/storage/google-drive/callback" if fake_drive else ""
        ),
    )
    app = create_app(settings, downloader=DownloaderService(settings, {Platform.YOUTUBE: adapter}))
    config = Config(str(CHECKOUT / "backend/alembic.ini"))
    config.set_main_option("script_location", str(CHECKOUT / "backend/alembic"))
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    queue = app.state.worker_manager.queue
    if fake_drive:
        with queue.sessions() as session:
            account = StorageAccountRepository(session).get_drive()
            known_account = account is None or account.provider_account_id in {None, "test-account"}
        if not known_account:
            app.state.engine.dispose()
            raise ValueError("Refusing a non-demo Drive account")
    core = DemoSourceCore(delay_seconds=source_delay)
    app.state.source_service = SourceService(
        queue,
        SourceAdapterRegistry((YouTubeSourceAdapter(core),)),
        clock=lambda: time.monotonic() * 600 / preview_ttl,
    )
    app.state.demo_adapter = adapter
    if fake_drive:
        drive = PersistentDrive(root)
        app.state.demo_drive = drive
        connection = queue.storage.connection
        connection.client_factory = lambda creds: drive

        def flow_factory(*args: object, **kwargs: object) -> FakeFlow:
            flow = FakeFlow()
            flow.credentials = credentials()
            return flow

        connection.flow_factory = flow_factory
        original_credentials = connection._credentials

        def offline_credentials() -> Credentials:
            # Keep configured/disconnected checks and validate every local read.
            # Fresh known mock credentials never initiate a Google token refresh.
            restored = original_credentials()
            if not known_demo_credentials(json.loads(restored.to_json())):
                raise StorageError("STORAGE_CREDENTIAL_FAILED")
            return credentials()

        connection._credentials = offline_credentials
        if connect_fake_drive:
            connection.start()
            connection.callback(next(iter(connection.states)), "demo-code", None)
            queue.storage.drive.set_root("root-folder")
    app.state.demo_seed_skipped = bool(seed_library and existing_database)
    adapter.seed_mode = True
    try:
        for number in range(1, (0 if existing_database else seed_library) + 1):
            jobs = queue.submit(
                [DownloadPayload(url=fixture_url(f"demo{number:07d}"), max_height=1080)]
            )
            # Seed only a fresh database before lifespan. Restarts preserve pending
            # attempts for the ordinary manager and its recovery lifecycle.
            claim = queue.claim()
            if claim is None or claim.id != jobs[0].id:
                raise RuntimeError("A fresh demo seed claim changed unexpectedly")
            execute_download(queue, claim, Event())
            if queue.get(jobs[0].id).status.value not in {"completed", "skipped_duplicate"}:
                raise RuntimeError("A deterministic seed job failed")
    finally:
        adapter.seed_mode = False
    return app


def watch_stop(path: Path, stop: Event, on_stop: Callable[[], None]) -> None:
    while not stop.wait(0.1):
        if path.exists():
            on_stop()
            return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(tempfile.gettempdir()) / "videovault-demo"
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--fake-drive", action="store_true")
    parser.add_argument("--connect-fake-drive", action="store_true")
    parser.add_argument("--seed-library", type=int, default=0)
    parser.add_argument("--source-delay", type=float, default=0)
    parser.add_argument("--preview-ttl", type=float, default=600)
    parser.add_argument("--stop-file", type=Path)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 0 <= args.seed_library <= 100:
        parser.error("Port must be 1-65535 and seed-library must be 0-100")
    if not 0 <= args.source_delay <= 120 or not 0 < args.preview_ttl <= 600:
        parser.error(
            "source-delay must be 0-120 and preview-ttl must be greater than 0, at most 600"
        )
    if args.connect_fake_drive and not args.fake_drive:
        parser.error("connect-fake-drive requires fake-drive")
    try:
        app = build_demo(
            args.root,
            port=args.port,
            fake_drive=args.fake_drive,
            connect_fake_drive=args.connect_fake_drive,
            source_delay=args.source_delay,
            seed_library=args.seed_library,
            preview_ttl=args.preview_ttl,
        )
    except ValueError as exc:
        parser.error(str(exc))
    root = args.root.expanduser().resolve()
    print("DETERMINISTIC DEMO: real API/SQLite/workers/media, offline platform/Drive adapters")
    print("Demo root:", root)
    if app.state.demo_seed_skipped:
        print("Existing demo database: seed-library skipped; persisted jobs are unchanged.")
    print("Quick Download normal:", fixture_url(NORMAL_ID))
    print("Slow/cancellable:", fixture_url(SLOW_ID))
    print("Fail once, then Retry:", fixture_url(FAIL_ID))
    print("Long title:", fixture_url(LONG_ID))
    print("Batch:", SOURCE, "or https://www.youtube.com/channel/" + CHANNEL + "/videos")
    if args.fake_drive:
        print("Fake Drive only. Connect in Storage; do not contact Google.")
        print("Use Continue-to-Google link state with the existing local callback and demo-code.")
        print("Callback query:", urlencode({"code": "demo-code", "state": "<link-state>"}))
    stop_path = args.stop_file if args.stop_file is not None else root / "STOP"
    if stop_path.exists():
        parser.error("Stop file already exists; remove your demo stop file before restarting")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port))
    stop = Event()
    watcher = Thread(
        target=watch_stop,
        args=(stop_path, stop, lambda: setattr(server, "should_exit", True)),
        daemon=True,
    )
    watcher.start()
    try:
        server.run()
    finally:
        stop.set()
        watcher.join(timeout=1)


if __name__ == "__main__":
    main()
