from app.core.errors import AppError

MESSAGES = {
    "SOURCE_URL_INVALID": "Enter a supported public channel or profile URL",
    "SOURCE_UNSUPPORTED": "This source URL form is not supported",
    "SOURCE_LIST_UNSUPPORTED": "Batch listing is unavailable for this platform; use Quick Download",
    "SOURCE_SORT_UNSUPPORTED": "This source cannot guarantee the requested ordering",
    "SOURCE_FILTER_UNSUPPORTED": "This source does not provide reliable metadata for that filter",
    "SOURCE_RESOLVE_FAILED": "Source preview could not be loaded; try again later",
    "SOURCE_PREVIEW_EXPIRED": "Preview expired or was used; preview the source again",
    "SOURCE_BUSY": "Source preview is busy; try again shortly",
    "BATCH_SELECTION_INVALID": "Select videos from the current source preview",
}


class SourceError(AppError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(MESSAGES[code])
