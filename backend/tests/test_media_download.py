import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.errors import MediaValidationError, MissingMediaToolError
from app.models.enums import Platform
from app.services.downloader.base import AdapterCapabilities, ProgressCallback
from app.services.downloader.errors import (
    DownloadFailedError,
    InvalidOutputDirectoryError,
    UnsupportedPlatformError,
)
from app.services.downloader.metadata import normalize_metadata
from app.services.downloader.models import (
    DownloadRequest,
    NormalizedVideo,
    ProgressEvent,
    ProgressPhase,
    VideoFormat,
)
from app.services.downloader.paths import remove_workspace
from app.services.downloader.service import DownloaderService
from app.services.media import probe
from tests.downloader_fixtures import FIXTURES, URL


class FakeAdapter:
    capabilities = AdapterCapabilities()

    def __init__(self, fixture: Path, *, fail: bool = False, escape: bool = False) -> None:
        self.fixture = fixture
        self.fail = fail
        self.escape = escape
        self.requests: list[DownloadRequest] = []

    def resolve(self, url: str) -> NormalizedVideo:
        return normalize_metadata(
            FIXTURES["combined"] | {"id": "../../CON", "title": "..\\NUL"}, Platform.YOUTUBE, url
        )

    def get_formats(self, video: NormalizedVideo) -> tuple[VideoFormat, ...]:
        return video.formats

    def download(
        self,
        video: NormalizedVideo,
        request: DownloadRequest,
        output_stem: Path,
        progress: ProgressCallback,
    ) -> Path:
        self.requests.append(request)
        path = output_stem.with_name(output_stem.name + ".mp4")
        if self.fail:
            path.with_suffix(".part").write_text("unfinished")
            raise DownloadFailedError()
        shutil.copyfile(self.fixture, path)
        progress(ProgressEvent(phase=ProgressPhase.PROCESSING))
        progress(ProgressEvent(phase=ProgressPhase.COMPLETED))
        return self.fixture if self.escape else path


def engine(tmp_path: Path, adapter: FakeAdapter, *, cap: int = 1080) -> DownloaderService:
    settings = Settings(
        _env_file=None, temp_storage_root=tmp_path / "temp", download_max_height=cap
    )
    return DownloaderService(settings, {Platform.YOUTUBE: adapter})


def test_real_probe(local_media: Path) -> None:
    result = probe.probe_video(local_media)
    assert (result.width, result.height) == (64, 48)
    assert result.duration_seconds > 0 and result.size_bytes > 0 and result.has_audio


def test_probe_rejects_embedded_network_requests(local_media: Path, tmp_path: Path) -> None:
    hits = []

    class SpyHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            hits.append(self.path)
            self.send_response(404)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), SpyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    playlist = tmp_path / "disguised.mp4"
    playlist.write_text(
        "#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\n"
        f"http://127.0.0.1:{server.server_port}/chunk.ts\n#EXT-X-ENDLIST\n"
    )
    try:
        with pytest.raises(MediaValidationError):
            probe.probe_video(playlist)
        assert hits == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("kind", ["missing", "empty", "garbage"])
def test_invalid_media(kind: str, tmp_path: Path) -> None:
    if kind == "garbage" and shutil.which("ffprobe") is None:
        pytest.skip("Real non-media validation requires globally installed ffprobe")
    file = tmp_path / "invalid.mp4"
    if kind != "missing":
        file.write_bytes(b"" if kind == "empty" else b"not a movie")
    with pytest.raises(MediaValidationError):
        probe.probe_video(file)


def test_missing_tool(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(probe.shutil, "which", lambda name: None)
    file = tmp_path / "media.mp4"
    file.write_bytes(b"some data")
    with pytest.raises(MissingMediaToolError):
        probe.probe_video(file)
    with pytest.raises(MissingMediaToolError):
        probe.require_tool("ffmpeg")


def test_safe_probe_invocation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    file = tmp_path / "movie;echo secret.mp4"
    file.write_bytes(b"media")
    monkeypatch.setattr(probe, "require_tool", lambda name: "ffprobe")
    calls = []

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(
            argv,
            0,
            '{"streams":[{"codec_type":"video","width":64,"height":48}],"format":{"duration":"0.3"}}',
            "",
        )

    monkeypatch.setattr(probe.subprocess, "run", run)
    assert probe.probe_video(file).height == 48
    argv, kwargs = calls[0]
    assert isinstance(argv, list) and argv[-1] == str(file.resolve())
    assert kwargs["shell"] is False and kwargs["timeout"] == 30


@pytest.mark.parametrize(
    "output",
    [
        "{}",
        "not json",
        '{"streams":[{"codec_type":"audio"}]}',
        '{"streams":[{"codec_type":"video","width":64,"height":48,"disposition":{"attached_pic":1}}],"format":{"duration":"0.3"}}',
        '{"streams":[{"codec_type":"video","width":64,"height":48}],"format":{"duration":"nan"}}',
    ],
)
def test_malformed_probe_result(
    output: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "candidate.mp4"
    path.write_bytes(b"candidate")
    monkeypatch.setattr(probe, "require_tool", lambda name: "ffprobe")
    monkeypatch.setattr(
        probe.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess([], 0, output, "secret"),
    )
    with pytest.raises(MediaValidationError) as error:
        probe.probe_video(path)
    assert "secret" not in str(error.value)


def test_probe_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "candidate.mp4"
    path.write_bytes(b"candidate")
    monkeypatch.setattr(probe, "require_tool", lambda name: "ffprobe")

    def timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired("secret-path", 30)

    monkeypatch.setattr(probe.subprocess, "run", timeout)
    with pytest.raises(MediaValidationError):
        probe.probe_video(path)


def test_fake_adapter_end_to_end(local_media: Path, tmp_path: Path) -> None:
    adapter = FakeAdapter(local_media)
    service = engine(tmp_path, adapter)
    request = service.prepare_request(URL)
    events: list[ProgressEvent] = []
    first = service.download(request, events.append)
    second = service.download(request)
    assert first.path.exists() and second.path.exists()
    assert first.path.parent != second.path.parent
    assert first.path.is_relative_to(tmp_path / "temp")
    assert (first.probe.width, first.probe.height) == (64, 48)
    assert [e.phase for e in events] == [
        ProgressPhase.RESOLVING,
        ProgressPhase.DOWNLOADING,
        ProgressPhase.PROCESSING,
        ProgressPhase.VALIDATING,
        ProgressPhase.COMPLETED,
    ]
    assert events[-1].percent == 100
    assert len(list((tmp_path / "temp").iterdir())) == 2


@pytest.mark.parametrize("mode", ["failure", "invalid", "escape", "height", "audio"])
def test_failure_cleanup_never_completed(mode: str, local_media: Path, tmp_path: Path) -> None:
    fixture = local_media
    if mode == "invalid":
        fixture = tmp_path / "invalid.txt"
        fixture.write_text("not media")
    adapter = FakeAdapter(fixture, fail=mode == "failure", escape=mode == "escape")
    service = engine(tmp_path, adapter, cap=40 if mode == "height" else 1080)
    request = service.prepare_request(URL, audio_enabled=mode != "audio")
    if mode in {"height", "audio"}:
        # Claimed metadata may lie; service must validate real dimensions/audio.
        adapter.get_formats = lambda video: (
            VideoFormat(
                format_id="fake",
                height=24,
                video_codec="mpeg4",
                audio_codec="none" if mode == "audio" else "aac",
            ),
        )
    events = []
    with pytest.raises((DownloadFailedError, MediaValidationError, InvalidOutputDirectoryError)):
        service.download(request, events.append)
    assert all(e.phase != ProgressPhase.COMPLETED for e in events)
    assert list((tmp_path / "temp").iterdir()) == []
    assert local_media.exists()


def test_confined_output(tmp_path: Path) -> None:
    service = engine(tmp_path, FakeAdapter(tmp_path / "unused"))
    for output in (tmp_path, tmp_path / "temp" / ".." / "escape"):
        with pytest.raises(InvalidOutputDirectoryError):
            service.prepare_request(URL, output_directory=output)
    assert not (tmp_path / "temp").exists()
    with pytest.raises(UnsupportedPlatformError):
        service.prepare_request("https://example.org/video")
    with pytest.raises(InvalidOutputDirectoryError):
        remove_workspace(tmp_path, tmp_path)


def test_configuration_cap_and_callback_failure(local_media: Path, tmp_path: Path) -> None:
    adapter = FakeAdapter(local_media)
    service = engine(tmp_path, adapter, cap=720)
    request = DownloadRequest(url=URL, max_height=1080, output_directory=tmp_path / "temp")

    def fail(event: ProgressEvent) -> None:
        raise RuntimeError("observer failure")

    result = service.download(request, fail)
    assert result.path.exists() and adapter.requests[0].max_height == 720
    assert service.prepare_request(URL).max_height == 720
