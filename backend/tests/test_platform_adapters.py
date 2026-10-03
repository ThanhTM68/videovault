import copy
import json
import shutil
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from yt_dlp import YoutubeDL
from yt_dlp.utils import ExtractorError, PostProcessingError

from app.core.config import Settings
from app.core.errors import AppError, MediaValidationError
from app.models.enums import Platform
from app.services.downloader import ytdlp
from app.services.downloader.adapters.common import PlatformAdapter
from app.services.downloader.adapters.registry import AdapterRegistry
from app.services.downloader.errors import (
    AuthenticationRequiredError,
    DownloadFailedError,
    DownloadUnavailableError,
    InvalidVideoUrlError,
    MetadataResolveError,
    UnsupportedPlatformError,
)
from app.services.downloader.models import ProgressPhase
from app.services.downloader.selector import select_formats
from app.services.downloader.service import DownloaderService

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures/downloader/platforms.json").read_text(encoding="utf-8")
)


def adapter_for(platform: Platform) -> PlatformAdapter:
    return AdapterRegistry().select(FIXTURES[platform.value]["url"])


def extractor_mock(monkeypatch: pytest.MonkeyPatch, info: dict) -> tuple[MagicMock, MagicMock]:
    extractor = MagicMock()
    extractor.__enter__.return_value = extractor
    extractor.extract_info.side_effect = lambda *a, **k: copy.deepcopy(info)
    factory = MagicMock(return_value=extractor)
    monkeypatch.setattr(ytdlp.yt_dlp, "YoutubeDL", factory)
    monkeypatch.setattr(ytdlp, "youtube_runtime_options", lambda: {})
    return factory, extractor


@pytest.mark.parametrize(
    "url,platform",
    [
        ("https://youtube.com/watch?v=TestVideo01&list=ignored", Platform.YOUTUBE),
        ("https://youtu.be/TestVideo01?si=ignored", Platform.YOUTUBE),
        ("https://m.youtube.com/shorts/TestVideo01", Platform.YOUTUBE),
        ("https://m.tiktok.com/@fixture/video/9007199254740993", Platform.TIKTOK),
        ("https://www.tiktok.com/share/video/9007199254740993", Platform.TIKTOK),
        ("https://vm.tiktok.com/Fixture/", Platform.TIKTOK),
        ("https://vt.tiktok.com/Fixture/", Platform.TIKTOK),
        ("https://www.tiktok.com/t/Fixture/", Platform.TIKTOK),
        ("https://douyin.com/video/9007199254740997", Platform.DOUYIN),
        ("https://instagram.com/reel/FixtureCode/", Platform.INSTAGRAM),
        ("https://www.instagram.com/p/FixtureCode/", Platform.INSTAGRAM),
        ("https://www.instagram.com/tv/FixtureCode/", Platform.INSTAGRAM),
        ("https://www.instagram.com/reels/FixtureCode/", Platform.INSTAGRAM),
        ("https://facebook.com/reel/9007199254741003", Platform.FACEBOOK),
        ("https://m.facebook.com/watch?v=9007199254741003", Platform.FACEBOOK),
        ("https://www.facebook.com/video.php?v=9007199254741003", Platform.FACEBOOK),
        ("https://www.facebook.com/fixture/videos/9007199254741003", Platform.FACEBOOK),
    ],
)
def test_registry_routes_supported_shapes(url: str, platform: Platform) -> None:
    adapter = AdapterRegistry().select(url)
    assert adapter.platform == platform and adapter.can_handle(url)
    assert sum(other.can_handle(url) for other in [adapter_for(p) for p in Platform]) == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/@fixture",
        "https://www.youtube.com/playlist?list=fixture",
        "https://www.youtube.com/results?search_query=fixture",
        "https://www.youtube.com/watch?v=a&v=b",
        "https://www.tiktok.com/@fixture",
        "https://www.tiktok.com/tag/fixture",
        "https://www.douyin.com/user/fixture",
        "https://v.douyin.com/Fixture",
        "https://instagram.com/fixture/",
        "https://instagram.com/stories/fixture/123",
        "https://instagram.com/explore/tags/fixture/",
        "https://www.facebook.com/fixture/",
        "https://www.facebook.com/watch/",
        "https://www.facebook.com/groups/fixture/",
        "https://fb.watch/Fixture",
        "https://www.facebook.com/flx/warn/?u=http%3A%2F%2F127.0.0.1",
        "https://example.com/video/123",
        "http://localhost/watch?v=x",
        "http://127.0.0.1/watch?v=x",
        "http://10.0.0.1/video/x",
        "http://192.168.0.1/video/x",
        "http://172.16.0.1/video/x",
        "http://169.254.169.254/latest/meta-data",
        "https://youtube.com.evil.example/watch?v=x",
        "https://evil.youtube.com/watch?v=x",
    ],
)
def test_registry_rejects_bulk_unknown_and_private_network_inputs(
    url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory, _ = extractor_mock(monkeypatch, {})
    with pytest.raises(UnsupportedPlatformError):
        DownloaderService(Settings(_env_file=None)).resolve(url)
    factory.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "file:///movie.mp4",
        "ftp://youtube.com/video",
        "http://[::1]/video",
        "not a URL",
        "https://secret@youtube.com/watch?v=x",
    ],
)
def test_registry_preserves_invalid_url_rejection(url: str) -> None:
    with pytest.raises(InvalidVideoUrlError):
        AdapterRegistry().select(url)


@pytest.mark.parametrize("platform", list(Platform))
def test_fixture_normalization_and_delegation(
    platform: Platform, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = FIXTURES[platform.value]
    original = copy.deepcopy(case["metadata"])
    factory, extractor = extractor_mock(monkeypatch, case["metadata"])
    adapter = adapter_for(platform)
    video = adapter.resolve(case["url"])
    assert video.platform == platform
    assert video.platform_video_id == str(case["metadata"]["id"])
    assert video.duration_seconds == case["metadata"]["duration"]
    assert video.title == case["metadata"]["title"]
    assert video.formats and select_formats(video.formats).video.height <= 1080
    assert video.height >= select_formats(video.formats).video.height
    assert adapter.get_formats(video) == video.formats
    assert case["metadata"] == original
    extractor.extract_info.assert_called_once_with(
        adapter.extraction_url(case["url"]), download=False
    )
    options = factory.call_args.args[0]
    assert options["allowed_extractors"] and not any(
        "generic" in name for name in options["allowed_extractors"]
    )
    assert not options["usenetrc"] and not options["allow_unplayable_formats"]
    assert not {"cookiefile", "cookiesfrombrowser", "username", "password"} & options.keys()


def test_platform_specific_creator_dates_and_ids() -> None:
    videos = {
        p: adapter_for(p).normalize(FIXTURES[p.value]["metadata"], FIXTURES[p.value]["url"])
        for p in Platform
    }
    youtube = videos[Platform.YOUTUBE]
    assert youtube.creator == "Fixture Channel" and youtube.creator_id == "UCFixtureChannel"
    assert youtube.creator_url.endswith("/channel/UCFixtureChannel")
    assert youtube.canonical_url == "https://www.youtube.com/watch?v=TestVideo01"
    tiktok = videos[Platform.TIKTOK]
    assert (
        tiktok.platform_video_id == "9007199254740993" and tiktok.creator_id == "9007199254740995"
    )
    assert tiktok.creator == "Fixture Creator" and tiktok.view_count == 9007199254740993
    assert tiktok.canonical_url.endswith("/@fixture_creator/video/9007199254740993")
    douyin = videos[Platform.DOUYIN]
    assert douyin.platform != tiktok.platform and douyin.creator == "Fixture Display Name"
    assert douyin.creator_id == "9007199254740999" and douyin.view_count is None
    instagram = videos[Platform.INSTAGRAM]
    assert instagram.creator == "fixture_creator" and instagram.creator_id is None
    assert instagram.view_count is None and instagram.canonical_url.endswith("/reel/FixtureCode/")
    facebook = videos[Platform.FACEBOOK]
    assert facebook.creator == "Fixture Page" and facebook.comment_count is None
    assert facebook.like_count is None and facebook.canonical_url.endswith(
        "/watch/?v=9007199254741003"
    )
    for platform in (Platform.YOUTUBE, Platform.TIKTOK, Platform.DOUYIN, Platform.INSTAGRAM):
        assert videos[platform].upload_date.isoformat() == "2026-01-02"
    assert facebook.upload_date is None and douyin.like_count == 0


@pytest.mark.parametrize("platform", list(Platform))
def test_missing_optional_metadata(platform: Platform) -> None:
    case = FIXTURES[platform.value]
    info = {k: v for k, v in case["metadata"].items() if k in {"id", "extractor_key"}}
    video = adapter_for(platform).normalize(info, case["url"])
    assert video.creator is None and video.creator_id is None and video.creator_url is None
    assert video.view_count is None and video.duration_seconds is None and video.upload_date is None
    assert (
        video.width is None and video.height is None and video.fps is None and video.formats == ()
    )


@pytest.mark.parametrize("platform", list(Platform))
def test_playlist_auth_and_changed_extractors_fail(
    platform: Platform, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = FIXTURES[platform.value]
    factory, extractor = extractor_mock(monkeypatch, case["metadata"])
    adapter = adapter_for(platform)
    for changes, category in [
        ({"_type": "playlist", "entries": []}, DownloadUnavailableError),
        ({"availability": "private"}, AuthenticationRequiredError),
        ({"has_drm": True}, DownloadUnavailableError),
        ({"extractor_key": "Generic"}, MetadataResolveError),
        ({"webpage_url": "https://other.example/video"}, MetadataResolveError),
    ]:
        extractor.extract_info.side_effect = None
        extractor.extract_info.return_value = case["metadata"] | changes
        with pytest.raises(category):
            adapter.resolve(case["url"])
    extractor.process_ie_result.assert_not_called()
    assert factory.call_count == 5


@pytest.mark.parametrize(
    "platform,message,category",
    [
        (Platform.YOUTUBE, "Confirm your age to watch this video", AuthenticationRequiredError),
        (Platform.TIKTOK, "Login required", AuthenticationRequiredError),
        (Platform.DOUYIN, "Fresh cookies are needed", AuthenticationRequiredError),
        (Platform.INSTAGRAM, "This private video is inaccessible", AuthenticationRequiredError),
        (Platform.FACEBOOK, "This video does not exist", DownloadUnavailableError),
        (Platform.TIKTOK, "Extractor changed unexpectedly", MetadataResolveError),
    ],
)
def test_restriction_errors_sanitized(
    platform: Platform,
    message: str,
    category: type[AppError],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    case = FIXTURES[platform.value]
    _, extractor = extractor_mock(monkeypatch, case["metadata"])
    extractor.extract_info.side_effect = ExtractorError(message + " secret-token")
    with pytest.raises(category) as error:
        adapter_for(platform).resolve(case["url"])
    assert "secret-token" not in str(error.value) and "secret-token" not in caplog.text


def test_postprocess_error_not_misclassified_as_unavailable() -> None:
    assert isinstance(
        ytdlp.map_extractor_error(PostProcessingError("Output video not found")),
        DownloadFailedError,
    )


def test_capabilities_and_failure_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    service = DownloaderService(Settings(_env_file=None))
    capabilities = service.capabilities()
    assert set(capabilities) == set(Platform)
    for capability in capabilities.values():
        assert capability.resolve_single and capability.download_single
        assert not any(
            [
                capability.list_profile_or_channel,
                capability.sort_newest,
                capability.sort_oldest,
                capability.sort_views,
                capability.filter_views,
                capability.filter_date,
                capability.filter_duration,
            ]
        )
    with pytest.raises(FrozenInstanceError):
        capabilities[Platform.YOUTUBE].sort_views = True
    capabilities.clear()
    assert len(service.capabilities()) == 5
    _, extractor = extractor_mock(monkeypatch, {})
    extractor.extract_info.side_effect = ExtractorError("TikTok login required")
    with pytest.raises(AuthenticationRequiredError):
        service.resolve(FIXTURES["tiktok"]["url"])
    extractor.extract_info.side_effect = None
    extractor.extract_info.return_value = FIXTURES["youtube"]["metadata"]
    assert service.resolve(FIXTURES["youtube"]["url"]).platform == Platform.YOUTUBE


def test_real_extractor_selection_and_challenge_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    with YoutubeDL(ytdlp._options()) as core_extractor:
        ytdlp._apply_policy(core_extractor, None)
        assert isinstance(core_extractor.get_info_extractor("TikTok"), ytdlp._RestrictedTikTokIE)
    for platform in Platform:
        adapter = adapter_for(platform)
        policy = adapter._policy()
        with YoutubeDL(ytdlp._options(policy)) as extractor:
            ytdlp._apply_policy(extractor, policy)
            loaded = {ie.IE_NAME.lower() for ie in extractor._ies.values()}
            assert loaded == {name.lower() for name in adapter.extractor_names}
            if platform == Platform.TIKTOK:
                guarded = extractor.get_info_extractor("TikTok")
                assert isinstance(guarded, ytdlp._RestrictedTikTokIE)
                monkeypatch.setattr(guarded, "_generate_blockbuster_headers", lambda: {})
                monkeypatch.setattr(guarded, "_get_universal_data", lambda *a: None)
                monkeypatch.setattr(
                    guarded,
                    "_download_webpage_handle",
                    lambda *a, **k: (
                        "synthetic challenge",
                        SimpleNamespace(
                            url=FIXTURES["tiktok"]["metadata"]["webpage_url"], extensions={}
                        ),
                    ),
                )
                with pytest.raises(AuthenticationRequiredError):
                    guarded._extract_web_data_and_status(
                        FIXTURES["tiktok"]["metadata"]["webpage_url"], "9007199254740993"
                    )
                assert list(extractor.cookiejar) == []


def test_metadata_edge_cases_remain_nullable_and_exact() -> None:
    case = FIXTURES["instagram"]
    info = case["metadata"] | {
        "uploader_url": "file:///secret",
        "upload_date": "broken",
        "timestamp": 1767313800,
        "duration": -1,
        "view_count": -5,
        "like_count": "unknown",
        "comment_count": 0,
        "width": None,
        "height": None,
        "fps": None,
        "formats": [],
    }
    video = adapter_for(Platform.INSTAGRAM).normalize(info, case["url"])
    assert video.creator_url is None and video.upload_date.isoformat() == "2026-01-02"
    assert video.duration_seconds is None and video.view_count is None and video.like_count is None
    assert video.comment_count == 0 and video.width is None and video.height is None
    youtube = FIXTURES["youtube"]
    username_only = youtube["metadata"] | {"channel_id": None, "channel": None}
    assert adapter_for(Platform.YOUTUBE).normalize(username_only, youtube["url"]).creator_id is None
    for invalid_id in (9.25, True, -1, "../../evil"):
        with pytest.raises(MetadataResolveError):
            adapter_for(Platform.INSTAGRAM).normalize(info | {"id": invalid_id}, case["url"])
    with pytest.raises(MetadataResolveError):
        adapter_for(Platform.INSTAGRAM).normalize(
            info | {"webpage_url": "file:///secret"}, case["url"]
        )


def test_platform_metadata_reuses_central_redaction() -> None:
    case = FIXTURES["tiktok"]
    info = case["metadata"] | {
        "http_headers": {"Authorization": "secret-token"},
        "cookies": "secret-token",
        "webpage_url": case["metadata"]["webpage_url"] + "?token=secret-token",
        "uploader_url": "https://www.tiktok.com/@fixture_creator?token=secret-token",
        "thumbnail": "https://images.example.org/thumb.jpg?signature=secret-token",
        "formats": [
            case["metadata"]["formats"][0]
            | {"url": "https://cdn.example.org/stream?token=secret-token"}
        ],
    }
    video = adapter_for(Platform.TIKTOK).normalize(info, case["url"])
    assert "secret-token" not in video.model_dump_json()
    assert len(json.dumps(video.raw_metadata)) < 4096


@pytest.mark.parametrize("platform", list(Platform))
def test_adapter_download_pipeline_with_real_probe(
    platform: Platform, local_media: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = FIXTURES[platform.value]
    _, extractor = extractor_mock(monkeypatch, case["metadata"])

    def write_candidate(info: dict, *, download: bool) -> dict:
        assert download
        # Match the core's fixed filename/container template, not remote titles.
        options = ytdlp.yt_dlp.YoutubeDL.call_args.args[0]
        selection = list(options["format"]({"formats": info["formats"]}))[0]
        assert int(selection["height"]) <= 1080
        output = Path(options["outtmpl"].replace(".%(ext)s", ".mp4"))
        shutil.copyfile(local_media, output)
        return info

    extractor.process_ie_result.side_effect = write_candidate
    service = DownloaderService(Settings(_env_file=None, temp_storage_root=tmp_path / "temp"))
    events = []
    result = service.download(service.prepare_request(case["url"]), events.append)
    assert result.video.platform == platform and result.path.is_relative_to(tmp_path / "temp")
    assert (result.probe.width, result.probe.height) == (64, 48)
    assert events[-1].phase == ProgressPhase.COMPLETED
    assert extractor.extract_info.call_count == 2


def test_refreshed_extractor_policy_checked_before_download(
    monkeypatch: pytest.MonkeyPatch, local_media: Path, tmp_path: Path
) -> None:
    case = FIXTURES["youtube"]
    _, extractor = extractor_mock(monkeypatch, case["metadata"])
    extractor.extract_info.side_effect = [
        case["metadata"],
        case["metadata"] | {"extractor_key": "Generic"},
    ]
    service = DownloaderService(Settings(_env_file=None, temp_storage_root=tmp_path / "temp"))
    with pytest.raises(MetadataResolveError):
        service.download(service.prepare_request(case["url"]))
    extractor.process_ie_result.assert_not_called()
    assert list((tmp_path / "temp").iterdir()) == []


def test_cap_and_actual_media_validation_preserved(
    monkeypatch: pytest.MonkeyPatch, local_media: Path, tmp_path: Path
) -> None:
    case = FIXTURES["facebook"]
    info = case["metadata"] | {
        "formats": [
            {"format_id": "small", "height": 24, "vcodec": "h264", "acodec": "aac", "ext": "mp4"}
        ]
    }
    _, extractor = extractor_mock(monkeypatch, info)

    def write(info: dict, *, download: bool) -> dict:
        options = ytdlp.yt_dlp.YoutubeDL.call_args.args[0]
        shutil.copyfile(local_media, Path(options["outtmpl"].replace(".%(ext)s", ".mp4")))
        return info

    extractor.process_ie_result.side_effect = write
    service = DownloaderService(
        Settings(_env_file=None, temp_storage_root=tmp_path / "temp", download_max_height=24)
    )
    events = []
    with pytest.raises(MediaValidationError):
        service.download(service.prepare_request(case["url"]), events.append)
    assert all(event.phase != ProgressPhase.COMPLETED for event in events)
    assert list((tmp_path / "temp").iterdir()) == []
