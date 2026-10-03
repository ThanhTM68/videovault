import copy
import functools
import subprocess
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError, PostProcessingError, UnsupportedError

from app.core.config import Settings
from app.core.errors import AppError
from app.models.enums import Platform
from app.services.downloader import ytdlp
from app.services.downloader.cancellation import DownloadCancelledError, cancellation_scope
from app.services.downloader.errors import (
    AuthenticationRequiredError,
    DownloadFailedError,
    DownloadUnavailableError,
    MetadataResolveError,
    UnsupportedPlatformError,
)
from app.services.downloader.metadata import normalize_metadata
from app.services.downloader.models import DownloadRequest, ProgressEvent, ProgressPhase
from app.services.downloader.service import DownloaderService
from app.services.media.probe import require_tool
from tests.downloader_fixtures import FIXTURES, URL


def mock_extractor(monkeypatch: pytest.MonkeyPatch, info: object) -> tuple[MagicMock, MagicMock]:
    instance = MagicMock()
    instance.__enter__.return_value = instance
    instance.extract_info.return_value = info
    factory = MagicMock(return_value=instance)
    monkeypatch.setattr(ytdlp.yt_dlp, "YoutubeDL", factory)
    # These tests replace extraction; runtime behavior has its own regressions.
    monkeypatch.setattr(ytdlp, "youtube_runtime_options", lambda: {})
    return factory, instance


def test_metadata_only_options(monkeypatch: pytest.MonkeyPatch) -> None:
    factory, instance = mock_extractor(monkeypatch, FIXTURES["combined"])
    adapter = ytdlp.YtDlpAdapter()
    video = adapter.resolve(URL)
    instance.extract_info.assert_called_once_with(URL, download=False)
    assert adapter.get_formats(video) == video.formats
    options = factory.call_args.args[0]
    assert options["noplaylist"] and not options["allow_unplayable_formats"]
    assert not options["usenetrc"] and options["socket_timeout"] == 30
    assert not {"cookiefile", "cookiesfrombrowser", "username", "password"} & options.keys()


@pytest.mark.parametrize(
    "exc,downloading,category",
    [
        (
            UnsupportedError("https://unsupported.org?token=secret-token"),
            False,
            UnsupportedPlatformError,
        ),
        (DownloadError("video unavailable secret-token"), False, DownloadUnavailableError),
        (
            ExtractorError("Sign in to see this private video secret-token"),
            False,
            AuthenticationRequiredError,
        ),
        (DownloadError("Login required secret-token"), True, AuthenticationRequiredError),
        (ExtractorError("Network timeout secret-token"), False, MetadataResolveError),
        (DownloadError("Network timeout secret-token"), True, DownloadFailedError),
        (PostProcessingError("processing error secret-token"), False, DownloadFailedError),
    ],
)
def test_error_mapping(exc: Exception, downloading: bool, category: type[AppError]) -> None:
    result = ytdlp.map_extractor_error(exc, downloading=downloading)
    assert isinstance(result, category) and "secret-token" not in str(result)
    assert result.details == {}


def test_wrapped_structured_error() -> None:
    cause = UnsupportedError("secret-token")
    error = DownloadError("failure", exc_info=(type(cause), cause, None))
    assert isinstance(ytdlp.map_extractor_error(error), UnsupportedPlatformError)


def test_resolve_failure_sanitized(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _, instance = mock_extractor(monkeypatch, FIXTURES["minimal"])
    instance.extract_info.side_effect = ExtractorError("network failure secret-token")
    with pytest.raises(MetadataResolveError) as error:
        ytdlp.YtDlpAdapter().resolve(URL)
    assert "secret-token" not in str(error.value) and "secret-token" not in caplog.text


def test_unknown_platform_never_extracts(monkeypatch: pytest.MonkeyPatch) -> None:
    factory, _ = mock_extractor(monkeypatch, {})
    with pytest.raises(UnsupportedPlatformError):
        ytdlp.YtDlpAdapter().resolve("https://example.org/video")
    factory.assert_not_called()


def test_download_selection_hooks_and_invocation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    factory, instance = mock_extractor(monkeypatch, FIXTURES["separate"])
    monkeypatch.setattr(ytdlp, "require_tool", lambda name: "ffmpeg")
    adapter = ytdlp.YtDlpAdapter()
    video = normalize_metadata(FIXTURES["separate"], Platform.YOUTUBE, URL)
    request = DownloadRequest(url=URL, output_directory=tmp_path)
    events: list[ProgressEvent] = []
    path = adapter.download(video, request, tmp_path / "safe", events.append)
    assert path == tmp_path / "safe.mp4"
    instance.extract_info.assert_called_once_with(URL, download=False)
    instance.process_ie_result.assert_called_once_with(FIXTURES["separate"], download=True)
    options = factory.call_args.args[0]
    chosen = list(options["format"]({"formats": FIXTURES["separate"]["formats"]}))[0]
    assert chosen["format_id"] == "1080+audio"
    assert len(chosen["requested_formats"]) == 2
    assert options["merge_output_format"] == "mp4"
    assert options["postprocessors"] == [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}]
    assert options["outtmpl"] == str(tmp_path / "safe") + ".%(ext)s"
    hook = options["progress_hooks"][0]
    hook(
        {
            "status": "downloading",
            "downloaded_bytes": 25,
            "total_bytes": 100,
            "speed": 1,
            "eta": 3,
            "filename": "secret-token",
        }
    )
    hook({"status": "downloading", "speed": float("nan"), "eta": -1})
    hook({"status": "finished"})
    assert events[0].percent == 25 and events[0].downloaded_bytes == 25
    assert events[1].speed is None and events[1].eta is None
    assert events[-1].phase == ProgressPhase.PROCESSING
    assert all(e.phase != ProgressPhase.COMPLETED for e in events)
    assert "secret-token" not in str(events)


@pytest.mark.parametrize(
    "info",
    [
        FIXTURES["private"],
        {"id": "fixture-video", "_type": "playlist", "entries": []},
        {"id": "other-video"},
    ],
)
def test_restrictions_checked_before_download(
    info: dict, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, instance = mock_extractor(monkeypatch, info)
    monkeypatch.setattr(ytdlp, "require_tool", lambda name: "ffmpeg")
    video = normalize_metadata(FIXTURES["combined"], Platform.YOUTUBE, URL)
    with pytest.raises((AuthenticationRequiredError, DownloadUnavailableError)):
        ytdlp.YtDlpAdapter().download(
            video,
            DownloadRequest(url=URL, output_directory=tmp_path),
            tmp_path / "safe",
            lambda event: None,
        )
    instance.process_ie_result.assert_not_called()


def test_postprocessing_failure_mapped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _, instance = mock_extractor(monkeypatch, FIXTURES["combined"])
    monkeypatch.setattr(ytdlp, "require_tool", lambda name: "ffmpeg")
    instance.process_ie_result.side_effect = PostProcessingError("secret-token")
    video = normalize_metadata(FIXTURES["combined"], Platform.YOUTUBE, URL)
    with pytest.raises(DownloadFailedError) as error:
        ytdlp.YtDlpAdapter().download(
            video,
            DownloadRequest(url=URL, output_directory=tmp_path),
            tmp_path / "safe",
            lambda event: None,
        )
    assert "secret-token" not in str(error.value)


@pytest.mark.parametrize("hook_name", ["progress_hooks", "postprocessor_hooks"])
def test_cancellation_reaches_shared_ytdlp_hooks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, hook_name: str
) -> None:
    factory, instance = mock_extractor(monkeypatch, FIXTURES["combined"])
    monkeypatch.setattr(ytdlp, "require_tool", lambda name: "ffmpeg")
    signal = threading.Event()

    def processing(*args: object, **kwargs: object) -> None:
        signal.set()
        raw = {"status": "downloading" if hook_name == "progress_hooks" else "started"}
        factory.call_args.args[0][hook_name][0](raw)

    instance.process_ie_result.side_effect = processing
    video = normalize_metadata(FIXTURES["combined"], Platform.YOUTUBE, URL)
    with cancellation_scope(signal), pytest.raises(DownloadCancelledError):
        ytdlp.YtDlpAdapter().download(
            video,
            DownloadRequest(url=URL, output_directory=tmp_path),
            tmp_path / "safe",
            lambda event: None,
        )


@pytest.mark.parametrize("mode", ["split", "progressive_mkv"])
def test_real_local_ytdlp_merge(
    local_media: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """Real yt-dlp/FFmpeg merge from loopback; extraction supplies synthetic metadata."""
    ffmpeg = require_tool("ffmpeg")
    for file, args in (
        ("video.mp4", ["-map", "0:v:0", "-c:v", "copy", "-an"]),
        ("audio.m4a", ["-map", "0:a:0", "-c:a", "copy", "-vn"]),
    ):
        subprocess.run(
            [ffmpeg, "-v", "error", "-i", str(local_media), *args, "-y", str(tmp_path / file)],
            check=True,
            capture_output=True,
            timeout=30,
            shell=False,
        )

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

    handler = functools.partial(QuietHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    info = FIXTURES["combined"] | {
        "extractor": "fixture",
        "extractor_key": "Fixture",
        "formats": [
            {
                "format_id": "v",
                "url": origin + "/video.mp4",
                "ext": "mp4",
                "protocol": "http",
                "vcodec": "mpeg4",
                "acodec": "none",
                "width": 64,
                "height": 48,
                "fps": 10,
            },
            {
                "format_id": "a",
                "url": origin + "/audio.m4a",
                "ext": "m4a",
                "protocol": "http",
                "vcodec": "none",
                "acodec": "aac",
                "abr": 128,
            },
        ],
    }
    if mode == "progressive_mkv":
        subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-i",
                str(local_media),
                "-c",
                "copy",
                "-y",
                str(tmp_path / "combined.mkv"),
            ],
            check=True,
            capture_output=True,
            timeout=30,
            shell=False,
        )
        info["formats"] = [
            info["formats"][0] | {"url": origin + "/combined.mkv", "ext": "mkv", "acodec": "aac"}
        ]

    class LocalExtractor(YoutubeDL):
        def extract_info(self, url: str, download: bool = True, **kwargs: object) -> dict:
            assert url == URL and download is False
            return copy.deepcopy(info)

    monkeypatch.setattr(ytdlp.yt_dlp, "YoutubeDL", LocalExtractor)
    monkeypatch.setattr(ytdlp, "youtube_runtime_options", lambda: {})
    service = DownloaderService(
        Settings(_env_file=None, temp_storage_root=tmp_path / "temp"),
        {Platform.YOUTUBE: ytdlp.YtDlpAdapter()},
    )
    events = []
    try:
        result = service.download(service.prepare_request(URL), events.append)
        assert result.path.suffix == ".mp4" and result.probe.has_audio
        assert (result.probe.width, result.probe.height) == (64, 48)
        assert events[-1].phase == ProgressPhase.COMPLETED
        assert any(e.phase == ProgressPhase.PROCESSING for e in events)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
