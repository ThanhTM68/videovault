from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse

from app.schemas.storage import ConnectResult, EmptyInput, FolderResult, RootInput, StorageStatus
from app.services.storage.errors import StorageError
from app.services.storage.service import StorageService

router = APIRouter(prefix="/storage")


def storage(request: Request) -> StorageService:
    return request.app.state.worker_manager.queue.storage


Storage = Annotated[StorageService, Depends(storage)]


@router.get("", response_model=StorageStatus)
def status(service: Storage) -> StorageStatus:
    return service.status()


@router.post("/google-drive/connect", response_model=ConnectResult)
def connect(service: Storage, body: EmptyInput) -> ConnectResult:
    return ConnectResult(authorization_url=service.connection.start())


@router.get("/google-drive/callback")
def callback(
    request: Request,
    service: Storage,
    state: Annotated[str, Query(max_length=256)] = "",
    code: Annotated[str | None, Query(max_length=8192)] = None,
    error: Annotated[str | None, Query(max_length=256)] = None,
) -> RedirectResponse:
    try:
        service.connection.callback(state, code, error)
        outcome = "drive=connected"
    except StorageError as exc:
        outcome = "drive=error&reason=" + exc.code
    return RedirectResponse(
        request.app.state.settings.frontend_origin + "/storage?" + outcome,
        status_code=303,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@router.post("/google-drive/disconnect", response_model=StorageStatus)
def disconnect(service: Storage, body: EmptyInput) -> StorageStatus:
    service.connection.disconnect()
    return service.status()


@router.put("/google-drive/root", response_model=FolderResult)
def select_root(service: Storage, body: RootInput) -> FolderResult:
    return service.drive.set_root(body.folder_id)


@router.post("/google-drive/root", response_model=FolderResult, status_code=201)
def create_root(service: Storage, body: EmptyInput) -> FolderResult:
    return service.drive.set_root()
