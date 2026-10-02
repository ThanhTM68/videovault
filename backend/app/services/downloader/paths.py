import re
import shutil
from pathlib import Path
from uuid import uuid4

from app.services.downloader.errors import InvalidOutputDirectoryError
from app.services.downloader.models import NormalizedVideo

_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"{p}{n}" for p in ("COM", "LPT") for n in range(1, 10))}
_RESERVED.update(f"{prefix}{digit}" for prefix in ("COM", "LPT") for digit in "¹²³")


def safe_component(value: str | None, limit: int = 64) -> str:
    # Also reject '%' so remote strings cannot introduce yt-dlp template directives.
    cleaned = re.sub(r"[^\w. -]", "_", value or "", flags=re.UNICODE)
    cleaned = cleaned[:limit].strip(" .") or "video"
    if cleaned.split(".", 1)[0].upper() in _RESERVED:
        cleaned = "_" + cleaned
    return cleaned


def video_filename(video: NormalizedVideo) -> str:
    identity = safe_component(video.platform_video_id, 48)
    title = safe_component(video.title)
    return f"{video.platform.value}_{identity}_{title}"


def confined_path(root: Path, path: Path) -> Path:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise InvalidOutputDirectoryError()
    return resolved


def create_workspace(root: Path, output_directory: Path) -> Path:
    destination = confined_path(root, output_directory)
    destination.mkdir(parents=True, exist_ok=True)
    workspace = destination / uuid4().hex
    workspace.mkdir()
    return workspace


def remove_workspace(root: Path, workspace: Path) -> None:
    # Remove only directories created by this service, never the configured root.
    safe = confined_path(root, workspace)
    if safe == root.resolve() or not re.fullmatch(r"[a-f0-9]{32}", workspace.name):
        raise InvalidOutputDirectoryError()
    if workspace.is_symlink() or safe != workspace:
        raise InvalidOutputDirectoryError()
    shutil.rmtree(safe)
