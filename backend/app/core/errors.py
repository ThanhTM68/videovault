from pydantic import JsonValue


class AppError(Exception):
    """Domain failure whose message and details are safe for public API responses."""

    code = "APPLICATION_ERROR"

    def __init__(self, message: str, *, details: dict[str, JsonValue] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = dict(details) if details is not None else {}


class NotFoundError(AppError):
    code = "NOT_FOUND"


class ConflictError(AppError):
    code = "CONFLICT"


class MediaValidationError(AppError):
    code = "MEDIA_VALIDATION_FAILED"

    def __init__(self) -> None:
        super().__init__("Downloaded output is not valid video media")


class MissingMediaToolError(AppError):
    code = "MEDIA_TOOL_UNAVAILABLE"

    def __init__(self) -> None:
        super().__init__("Required FFmpeg or ffprobe executable is unavailable")
