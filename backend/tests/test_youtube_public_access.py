"""Deterministic regressions; never contact YouTube in CI."""

import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from yt_dlp import YoutubeDL, dependencies
from yt_dlp.utils import DownloadError, ExtractorError

from app.core.errors import AppError
from app.models.enums import Platform
from app.services.downloader import runtime, ytdlp
from app.services.downloader.adapters.registry import AdapterRegistry
from app.services.downloader.errors import (
    AuthenticationRequiredError,
    ExtractorRuntimeUnavailableError,
)
from app.services.downloader.metadata import check_single_video
from tests.downloader_fixtures import FIXTURES, URL


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("downloading", [False, True])
def test_bot_check_is_not_content_auth(wrapped: bool, downloading: bool) -> None:
    cause = ExtractorError("Sign in to confirm you're not a bot secret-token")
    exc = DownloadError(str(cause), exc_info=(type(cause), cause, None) if wrapped else None)
    error = ytdlp.map_extractor_error(exc, downloading=downloading)
    assert error.code == "PLATFORM_ACCESS_BLOCKED"
    assert "may still be public" in str(error)
    assert error.details == {} and "secret-token" not in str(error)


@pytest.mark.parametrize(
    "availability", ["private", "premium_only", "subscriber_only", "needs_auth", "members-only"]
)
def test_content_restrictions_remain_auth(availability: str) -> None:
    with pytest.raises(AuthenticationRequiredError):
        check_single_video(FIXTURES["combined"] | {"availability": availability})


def extractor_double(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    instance = MagicMock()
    instance.__enter__.return_value = instance
    instance.extract_info.return_value = FIXTURES["combined"]
    factory = MagicMock(return_value=instance)
    monkeypatch.setattr(ytdlp.yt_dlp, "YoutubeDL", factory)
    return factory


def test_youtube_missing_node_is_safe_and_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil

    factory = extractor_double(monkeypatch)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(AppError) as error:
        ytdlp.YtDlpAdapter().resolve(URL)
    assert error.value.code == "EXTRACTOR_RUNTIME_UNAVAILABLE"
    factory.assert_not_called()


@pytest.fixture
def supported_runtime(monkeypatch: pytest.MonkeyPatch) -> str:
    node = "fixture-node"
    monkeypatch.setattr(runtime.shutil, "which", lambda name: node if name == "node" else None)
    monkeypatch.setattr(
        runtime.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="v22.0.0\n")
    )
    return node


def test_youtube_enables_official_node_options(
    monkeypatch: pytest.MonkeyPatch, supported_runtime: str
) -> None:
    factory = extractor_double(monkeypatch)
    ytdlp.YtDlpAdapter().resolve(URL)
    options = factory.call_args.args[0]
    assert set(options["js_runtimes"]) == {"node"}
    assert options["js_runtimes"]["node"]["path"] == supported_runtime
    assert not options.get("remote_components")

    # The real pinned library must accept the effective public Python API shape.
    policy = AdapterRegistry().select(URL)._policy()
    with YoutubeDL(ytdlp._options(policy, platform=Platform.YOUTUBE)) as extractor:
        assert extractor.params["js_runtimes"] == {"node": {"path": supported_runtime}}
        assert extractor.params["remote_components"] == set()
        assert set(extractor._js_runtimes) == {"node"}
        assert extractor._js_runtimes["node"]._path == supported_runtime
        assert {ie.IE_NAME.lower() for ie in extractor._ies.values()} == {"youtube"}


@pytest.mark.parametrize("node_version", ["v20.19.0\n", "v21.7.0\n", "unknown\n"])
def test_old_or_invalid_node_fails_before_network(
    monkeypatch: pytest.MonkeyPatch, supported_runtime: str, node_version: str
) -> None:
    factory = extractor_double(monkeypatch)
    monkeypatch.setattr(
        runtime.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=node_version)
    )
    with pytest.raises(ExtractorRuntimeUnavailableError):
        ytdlp.YtDlpAdapter().resolve(URL)
    factory.assert_not_called()


@pytest.mark.parametrize(
    "failure", [FileNotFoundError("secret-path"), subprocess.TimeoutExpired("secret-path", 5)]
)
def test_node_probe_failures_are_bounded_and_safe(
    monkeypatch: pytest.MonkeyPatch, supported_runtime: str, failure: Exception
) -> None:
    probe = MagicMock(side_effect=failure)
    monkeypatch.setattr(runtime.subprocess, "run", probe)
    with pytest.raises(ExtractorRuntimeUnavailableError) as error:
        ytdlp.YtDlpAdapter().resolve(URL)
    assert "secret-path" not in str(error.value) and error.value.details == {}
    assert probe.call_args.args[0] == [supported_runtime, "--version"]
    assert probe.call_args.kwargs["timeout"] == 5 and probe.call_args.kwargs["shell"] is False


@pytest.mark.parametrize("ejs", [None, SimpleNamespace(version="0.7.0")])
def test_missing_or_incompatible_ejs_is_lazy_and_safe(
    monkeypatch: pytest.MonkeyPatch, supported_runtime: str, ejs: object
) -> None:
    factory = extractor_double(monkeypatch)
    monkeypatch.setattr(dependencies, "yt_dlp_ejs", ejs)
    with pytest.raises(ExtractorRuntimeUnavailableError):
        ytdlp.YtDlpAdapter().resolve(URL)
    factory.assert_not_called()


def test_broken_local_ejs_fails_before_network(
    monkeypatch: pytest.MonkeyPatch, supported_runtime: str
) -> None:
    factory = extractor_double(monkeypatch)
    monkeypatch.setattr(runtime, "import_module", MagicMock(side_effect=ImportError("secret-path")))
    with pytest.raises(ExtractorRuntimeUnavailableError) as error:
        ytdlp.YtDlpAdapter().resolve(URL)
    assert "secret-path" not in str(error.value)
    factory.assert_not_called()


def test_partial_ejs_install_in_fresh_process_returns_setup_error() -> None:
    script = """
import json, sys
from unittest.mock import patch
from types import SimpleNamespace
from app.services.downloader.runtime import youtube_runtime_options
from app.core.errors import AppError
sys.modules['yt_dlp_ejs.yt.solver'] = None
with patch('shutil.which', return_value='fixture-node'), patch(
    'subprocess.run', return_value=SimpleNamespace(stdout='v22.0.0')):
    try:
        youtube_runtime_options()
    except AppError as error:
        print(json.dumps({'code': error.code, 'details': error.details}))
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=30, shell=False
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"code": "EXTRACTOR_RUNTIME_UNAVAILABLE", "details": {}}


@pytest.mark.parametrize(
    "phrase", ["sign in", "cookies", "authentication service failed", "challenge failed"]
)
def test_ambiguous_fragments_do_not_claim_content_auth(phrase: str) -> None:
    assert ytdlp.map_extractor_error(DownloadError(phrase)).code == "METADATA_RESOLVE_FAILED"


@pytest.mark.parametrize(
    "phrase",
    [
        "No supported JavaScript runtime could be found",
        "No usable challenge solver lib script available",
    ],
)
def test_specific_runtime_error_text(phrase: str) -> None:
    assert ytdlp.map_extractor_error(DownloadError(phrase)).code == "EXTRACTOR_RUNTIME_UNAVAILABLE"


@pytest.mark.parametrize(
    "phrase",
    [
        "You do not have permission to view this post. Log into an account that has access",
        "This content is only available for registered users who follow this account",
        "This video is private",
        "Join this channel to get access to members-only content",
    ],
)
def test_precise_upstream_access_restrictions_remain_auth(phrase: str) -> None:
    assert ytdlp.map_extractor_error(DownloadError(phrase)).code == "AUTHENTICATION_REQUIRED"


def test_other_platform_and_flat_source_options_do_not_probe_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = MagicMock(side_effect=AssertionError("Unexpected YouTube runtime probe"))
    monkeypatch.setattr(ytdlp, "youtube_runtime_options", probe)
    assert "js_runtimes" not in ytdlp._options(platform=Platform.TIKTOK)
    assert "js_runtimes" not in ytdlp._options()
    probe.assert_not_called()
