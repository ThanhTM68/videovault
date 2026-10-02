import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.errors import AppError
from app.models.enums import Platform
from app.services.downloader.errors import (
    AuthenticationRequiredError,
    DownloadUnavailableError,
    InvalidVideoUrlError,
    MetadataResolveError,
)
from app.services.downloader.metadata import normalize_metadata
from app.services.downloader.models import (
    DownloadRequest,
    ProgressEvent,
    ProgressPhase,
    VideoFormat,
)
from app.services.downloader.paths import safe_component, video_filename
from app.services.downloader.platform import detect_platform, validate_video_url
from app.services.downloader.progress import ProgressReporter
from app.services.downloader.selector import select_formats
from tests.downloader_fixtures import FIXTURES, URL


@pytest.mark.parametrize(
    "url,expected",
    [
        (URL, Platform.YOUTUBE),
        ("https://youtu.be/video", Platform.YOUTUBE),
        ("https://youtube.com/shorts/video", Platform.YOUTUBE),
        ("https://m.tiktok.com/@creator/video/123", Platform.TIKTOK),
        ("https://www.douyin.com/video/123", Platform.DOUYIN),
        ("https://instagram.com/reel/123", Platform.INSTAGRAM),
        ("http://www.facebook.com/reel/123", Platform.FACEBOOK),
        ("https://fb.watch/123", Platform.FACEBOOK),
        ("https://example.org/video", "unknown"),
        ("https://youtube.com.evil.org/video", "unknown"),
        ("https://notyoutube.com/video", "unknown"),
    ],
)
def test_classification(url: str, expected: Platform | str) -> None:
    assert detect_platform(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "ftp://youtube.com/video",
        "file:///C:/movie.mp4",
        "C:\\movie.mp4",
        "/tmp/movie",
        "not a url",
        "https:///video",
        "https://",
        "https://youtube.com:bad/watch",
        "https://user:secret@youtube.com/watch",
        "https://youtube.com\\@evil.org",
        "https://youtube.com/\nwatch",
        "https://-youtube.com/watch",
        "https://youtube..com",
        "https://youtube.com:444/watch",
        "https://youtube.com /watch",
        "https://youtube.com:/watch",
    ],
)
def test_invalid_url(url: str) -> None:
    with pytest.raises(InvalidVideoUrlError):
        validate_video_url(url)


def test_url_normalization_and_shell_metacharacters() -> None:
    assert (
        validate_video_url("HTTPS://YOUTUBE.COM/watch?v=x#section")
        == "https://youtube.com/watch?v=x"
    )
    assert validate_video_url("https://youtube.com/watch?v=x;echo%20hello").endswith(
        "x;echo%20hello"
    )


def test_request_defaults_and_validation(tmp_path: Path) -> None:
    request = DownloadRequest(url=URL, output_directory=tmp_path)
    assert (request.max_height, request.preferred_container, request.audio_enabled) == (
        1080,
        "mp4",
        True,
    )
    for options in (
        {"max_height": 2160},
        {"max_height": 0},
        {"max_height": True},
        {"audio_enabled": "false"},
        {"preferred_container": "../mp4"},
        {"url": "file:///secret"},
        {"options": {"cookiesfrombrowser": "chrome"}},
    ):
        with pytest.raises(ValidationError) as error:
            DownloadRequest(**({"url": URL, "output_directory": tmp_path} | options))
        assert "file:///secret" not in str(error.value)


def test_complete_and_minimal_metadata() -> None:
    video = normalize_metadata(FIXTURES["combined"], Platform.YOUTUBE, URL)
    assert video.platform_video_id == "fixture-video"
    assert video.creator_id == "fixture-creator"
    assert video.upload_date.isoformat() == "2026-01-02"
    assert video.duration_seconds == 0.3
    assert (video.width, video.height, video.fps) == (64, 48, 10)
    assert (video.view_count, video.like_count, video.comment_count) == (500, 30, 4)
    assert video.formats[0].has_audio
    minimal = normalize_metadata(FIXTURES["minimal"], Platform.YOUTUBE, URL)
    assert minimal.title is None and minimal.creator is None and minimal.duration_seconds is None
    assert minimal.upload_date is None and minimal.formats == ()


def test_metadata_bounds_and_redaction() -> None:
    raw = FIXTURES["combined"] | {
        "http_headers": {"Authorization": "secret-token"},
        "cookies": "secret-token",
        "url": "https://cdn.example.org/stream?signature=secret-token",
        "webpage_url": URL + "&token=secret-token",
        "thumbnail": "https://cdn.example.org/image?signature=secret-token",
        "title": "x" * 100000,
        "description": "x" * 100000,
        "width": -1,
        "view_count": "unknown",
        "fps": float("nan"),
        "upload_date": "invalid",
    }
    video = normalize_metadata(raw, Platform.YOUTUBE, URL)
    serialized = video.model_dump_json()
    assert "secret-token" not in serialized and "http_headers" not in serialized
    assert len(video.raw_metadata["title"]) == 256
    assert len(video.title) == 4096 and len(video.description) == 16384
    assert video.width is None and video.fps is None and video.view_count is None
    assert video.upload_date is None
    assert len(json.dumps(video.raw_metadata)) < 4096


def test_metadata_preserves_identity_and_counts() -> None:
    with pytest.raises(MetadataResolveError):
        normalize_metadata({"id": "x" * 513}, Platform.YOUTUBE, URL)
    count = 2**53 + 1
    video = normalize_metadata(
        {"id": "x", "view_count": count, "upload_date": "20260101extra"}, Platform.YOUTUBE, URL
    )
    assert video.view_count == count and video.upload_date is None


def test_duplicate_format_ids_rejected() -> None:
    formats = [FIXTURES["combined"]["formats"][0]] * 2
    with pytest.raises(MetadataResolveError):
        normalize_metadata({"id": "x", "formats": formats}, Platform.YOUTUBE, URL)


@pytest.mark.parametrize(
    "key,error",
    [("private", AuthenticationRequiredError), ("unavailable", DownloadUnavailableError)],
)
def test_metadata_restricted(key: str, error: type[AppError]) -> None:
    with pytest.raises(error):
        normalize_metadata(FIXTURES[key], Platform.YOUTUBE, URL)


@pytest.mark.parametrize("raw", [{}, {"id": "x", "entries": []}, {"id": "x", "is_live": True}])
def test_metadata_rejects_missing_identity_playlists_live(raw: dict) -> None:
    with pytest.raises((MetadataResolveError, DownloadUnavailableError)):
        normalize_metadata(raw, Platform.YOUTUBE, URL)


def fmt(
    height: int | None,
    *,
    identity: str = "v",
    audio: str = "aac",
    ext: str = "mp4",
    drm: bool = False,
) -> VideoFormat:
    return VideoFormat(
        format_id=identity,
        height=height,
        video_codec="h264",
        audio_codec=audio,
        extension=ext,
        has_drm=drm,
    )


@pytest.mark.parametrize(
    "heights,expected",
    [([2160, 1080, 720], 1080), ([1080, 720], 1080), ([720], 720), ([1440, 720], 720)],
)
def test_quality_cap(heights: list[int], expected: int) -> None:
    selection = select_formats([fmt(h, identity=str(h)) for h in heights])
    assert selection.video.height == expected


def test_separate_streams_preserve_quality() -> None:
    video = normalize_metadata(FIXTURES["separate"], Platform.YOUTUBE, URL)
    selection = select_formats(video.formats)
    assert selection.video.format_id == "1080" and selection.audio.format_id == "audio"
    silent = select_formats(video.formats, audio_enabled=False)
    assert silent.video.format_id == "1080" and silent.audio is None


def test_compatibility_is_only_a_quality_tiebreaker() -> None:
    formats = [fmt(720), fmt(1080, identity="webm", ext="webm")]
    assert select_formats(formats).video.format_id == "webm"
    formats += [fmt(1080, identity="mp4")]
    assert select_formats(reversed(formats)).video.format_id == "mp4"


@pytest.mark.parametrize(
    "formats", [[], [fmt(None)], [fmt(2160)], [fmt(720, drm=True)], [fmt(720, audio="none")]]
)
def test_no_usable_formats(formats: list[VideoFormat]) -> None:
    with pytest.raises(DownloadUnavailableError):
        select_formats(formats)


@pytest.mark.parametrize(
    "remote",
    [
        "../../evil",
        "..\\..\\evil",
        "CON",
        "NUL",
        "a/b",
        "a\\b",
        "COM1.txt",
        "LPT9",
        "COM¹",
        "LPT².txt",
        "%(title)s",
        "x" * 10000,
        '<>:"|?*',
        "...",
    ],
)
def test_safe_filenames(remote: str, tmp_path: Path) -> None:
    component = safe_component(remote)
    assert component and len(component) <= 65
    assert component.rstrip(" .") == component
    assert not any(char in component for char in '<>:"/\\|?*%')
    assert component.split(".")[0].upper() not in {"CON", "NUL", "COM1", "LPT9", "COM¹", "LPT²"}
    video = normalize_metadata({"id": remote[:512], "title": remote}, Platform.YOUTUBE, URL)
    path = tmp_path / video_filename(video)
    assert path.parent == tmp_path and len(path.name) < 140


def test_callback_failure_isolated(caplog: pytest.LogCaptureFixture) -> None:
    calls = []

    def fail(event: ProgressEvent) -> None:
        calls.append(event)
        raise RuntimeError("secret-token")

    reporter = ProgressReporter(fail)
    reporter(ProgressEvent(phase=ProgressPhase.DOWNLOADING))
    reporter(ProgressEvent(phase=ProgressPhase.COMPLETED))
    assert len(calls) == 1 and "secret-token" not in caplog.text


def test_downloader_error_uses_existing_api_envelope(application: FastAPI) -> None:
    @application.get("/test-download-error")
    def fail() -> None:
        raise AuthenticationRequiredError()

    with TestClient(application) as client:
        response = client.get("/test-download-error")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert response.json()["error"]["details"] == {}
