import json
import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.core.errors import MediaValidationError, MissingMediaToolError


@dataclass(frozen=True)
class ProbeResult:
    duration_seconds: float
    width: int
    height: int
    size_bytes: int
    has_audio: bool


def require_tool(name: str) -> str:
    if name not in {"ffmpeg", "ffprobe"}:
        raise ValueError("Unsupported media tool")
    executable = shutil.which(name)
    if executable is None:
        raise MissingMediaToolError()
    return executable


def probe_video(path: Path) -> ProbeResult:
    """Inspect local video through argv, never a shell or extension heuristic."""
    try:
        if not path.is_file() or path.stat().st_size <= 0:
            raise MediaValidationError()
        size = path.stat().st_size
        result = subprocess.run(
            [
                require_tool("ffprobe"),
                "-v",
                "error",
                "-protocol_whitelist",
                "file",
                "-format_whitelist",
                "mov,matroska,webm",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(path.resolve()),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
            shell=False,
        )
        if result.returncode:
            raise MediaValidationError()
        metadata = json.loads(result.stdout)
        streams = metadata.get("streams", [])
        video = next(
            s
            for s in streams
            if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
        )
        duration = float(metadata.get("format", {}).get("duration") or video.get("duration"))
        width, height = int(video["width"]), int(video["height"])
        if not math.isfinite(duration) or duration <= 0 or width <= 0 or height <= 0:
            raise MediaValidationError()
        return ProbeResult(
            duration, width, height, size, any(s.get("codec_type") == "audio" for s in streams)
        )
    except FileNotFoundError:
        raise MissingMediaToolError() from None
    except (
        OSError,
        subprocess.TimeoutExpired,
        ValueError,
        TypeError,
        KeyError,
        StopIteration,
        AttributeError,
    ):
        raise MediaValidationError() from None
