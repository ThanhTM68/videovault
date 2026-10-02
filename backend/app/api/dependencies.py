from fastapi import Request

from app.core.config import Settings


def get_settings(request: Request) -> Settings:
    """Use the current app's validated settings; no global settings cache."""
    settings: Settings = request.app.state.settings
    return settings
