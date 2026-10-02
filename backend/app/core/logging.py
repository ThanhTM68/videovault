import logging

from app.core.config import Settings


def configure_logging(settings: Settings) -> None:
    """Configure only the application logger without replacing host/test handlers."""
    logger = logging.getLogger("app")
    logger.setLevel(logging.DEBUG if settings.app_env == "development" else logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
