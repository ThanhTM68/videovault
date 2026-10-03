"""Lazy local YouTube prerequisites for the pinned yt-dlp release; no network I/O."""

import re
import shutil
import subprocess
from importlib import import_module
from importlib.metadata import version

from app.services.downloader.errors import ExtractorRuntimeUnavailableError


def youtube_runtime_options() -> dict[str, object]:
    # These version authorities belong to the pinned dependency. Review on upgrade.
    try:
        from yt_dlp import dependencies
        from yt_dlp.utils._jsruntime import NodeJsRuntime
    except ImportError:
        raise ExtractorRuntimeUnavailableError() from None

    node = shutil.which("node")
    if node is None:
        raise ExtractorRuntimeUnavailableError()
    try:
        result = subprocess.run(
            [node, "--version"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
            shell=False,
        )
        match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)\s*", result.stdout)
        if match is None or tuple(map(int, match.groups())) < NodeJsRuntime.MIN_SUPPORTED_VERSION:
            raise ExtractorRuntimeUnavailableError()
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        raise ExtractorRuntimeUnavailableError() from None

    try:
        # Importing this third-party package may itself load the EJS scripts.
        from yt_dlp.extractor.youtube.jsc._builtin.vendor import VERSION

        # Check the package that yt-dlp will actually consume, including cached absence
        # after installation into an already running process (requires restart).
        ejs = dependencies.yt_dlp_ejs
        if ejs is None or ejs.version != VERSION or version("yt-dlp-ejs") != VERSION:
            raise ExtractorRuntimeUnavailableError()
        solver = import_module("yt_dlp_ejs.yt.solver")
        if not solver.core() or not solver.lib():
            raise ExtractorRuntimeUnavailableError()
    except Exception:
        # Broken/missing third-party package diagnostics are not public.
        raise ExtractorRuntimeUnavailableError() from None
    return {"js_runtimes": {"node": {"path": node}}, "remote_components": []}
