from app.core.errors import AppError


class DownloaderError(AppError):
    public_message = "Download operation failed"

    def __init__(self) -> None:
        super().__init__(self.public_message)


class UnsupportedPlatformError(DownloaderError):
    code = "UNSUPPORTED_PLATFORM"
    public_message = "This URL is not supported by the configured adapters"


class InvalidVideoUrlError(DownloaderError):
    code = "INVALID_VIDEO_URL"
    public_message = "A valid HTTP or HTTPS video URL is required"


class MetadataResolveError(DownloaderError):
    code = "METADATA_RESOLVE_FAILED"
    public_message = "Video metadata could not be resolved"


class DownloadUnavailableError(DownloaderError):
    code = "DOWNLOAD_UNAVAILABLE"
    public_message = "A usable public video format is unavailable"


class AuthenticationRequiredError(DownloaderError):
    code = "AUTHENTICATION_REQUIRED"
    public_message = "This content requires authentication or access permission"


class PlatformAccessBlockedError(DownloaderError):
    code = "PLATFORM_ACCESS_BLOCKED"
    public_message = (
        "The platform blocked anonymous access from this environment. "
        "The video may still be public. "
        "Try again later or from a normal network connection."
    )


class ExtractorRuntimeUnavailableError(DownloaderError):
    code = "EXTRACTOR_RUNTIME_UNAVAILABLE"
    public_message = (
        "YouTube extraction requires supported Node.js and the matching local EJS package. "
        "Install the documented backend dependencies and runtime, then restart the backend."
    )


class DownloadFailedError(DownloaderError):
    code = "DOWNLOAD_FAILED"
    public_message = "The download or container processing failed"


class InvalidOutputDirectoryError(DownloaderError):
    code = "INVALID_OUTPUT_DIRECTORY"
    public_message = "Output must be inside configured temporary storage"
