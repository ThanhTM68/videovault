from app.core.errors import AppError

MESSAGES = {
    "STORAGE_NOT_CONFIGURED": "Google Drive is not configured",
    "STORAGE_NOT_CONNECTED": "Google Drive is disconnected; connect in Storage settings",
    "STORAGE_ROOT_INVALID": "Choose an accessible Google Drive folder before uploading",
    "STORAGE_UPLOAD_FAILED": "The storage upload could not be completed",
    "STORAGE_DELETE_FAILED": "The stored object could not be deleted",
    "STORAGE_UNAVAILABLE": "Storage is temporarily unavailable; try again later",
    "STORAGE_PERMISSION_DENIED": "Storage access was denied",
    "STORAGE_KEY_INVALID": "The storage identifier is invalid",
    "STORAGE_UNMANAGED_OBJECT": "This object is not managed VideoVault media",
    "STORAGE_CREDENTIAL_FAILED": "Private credential storage could not be accessed",
    "STORAGE_ACCOUNT_MISMATCH": "Reconnect the original Google Drive account",
    "STORAGE_ACCOUNT_AMBIGUOUS": "Multiple Drive account records require operator review",
    "OAUTH_STATE_INVALID": "The connection request expired or was already used; connect again",
    "OAUTH_FAILED": "Google Drive connection failed; please connect again",
    "OAUTH_DENIED": "Google Drive consent was declined",
}


class StorageError(AppError):
    def __init__(self, code: str = "STORAGE_UNAVAILABLE") -> None:
        self.code = code
        super().__init__(MESSAGES[code])
