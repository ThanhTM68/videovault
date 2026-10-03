import logging

from app.core.config import Settings


class OAuthAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # HTTP clients used by integrations/tests can also log callback URLs.
        if record.name == "httpx" and isinstance(record.args, tuple):
            record.args = tuple(
                str(value).split("?", 1)[0]
                if "/api/v1/storage/google-drive/callback?" in str(value)
                else value
                for value in record.args
            )
        if isinstance(record.args, tuple) and len(record.args) == 5:
            address, method, path, version, status = record.args
            if str(path).split("?", 1)[0] == "/api/v1/storage/google-drive/callback":
                record.args = (address, method, str(path).split("?", 1)[0], version, status)
        return True


def configure_logging(settings: Settings) -> None:
    """Configure only the application logger without replacing host/test handlers."""
    logger = logging.getLogger("app")
    logger.setLevel(logging.DEBUG if settings.app_env == "development" else logging.INFO)
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, OAuthAccessFilter) for item in access.filters):
        access.addFilter(OAuthAccessFilter())
    http = logging.getLogger("httpx")
    if not any(isinstance(item, OAuthAccessFilter) for item in http.filters):
        http.addFilter(OAuthAccessFilter())
    # SDK debug logging can contain OAuth request/response bodies.
    for name in (
        "oauthlib",
        "requests_oauthlib",
        "google.auth",
        "google_auth_oauthlib",
        "googleapiclient",
    ):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
