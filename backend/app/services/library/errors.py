from app.core.errors import AppError


class LibraryFileError(AppError):
    def __init__(self, code: str = "FILE_OPERATION_FAILED") -> None:
        self.code = code
        super().__init__(
            "File is outside managed storage"
            if code == "FILE_OUTSIDE_MANAGED_ROOT"
            else "The managed file operation could not be completed"
        )
