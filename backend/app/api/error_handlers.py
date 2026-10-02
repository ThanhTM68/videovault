import logging
import traceback
from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import JsonValue
from starlette.exceptions import HTTPException

from app.api.dependencies import get_settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.schemas.errors import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


def error_response(
    status: int,
    code: str,
    message: str,
    details: dict[str, JsonValue] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message, details=details or {}))
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"), headers=headers)


async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    status = 400
    if isinstance(exc, NotFoundError):
        status = 404
    elif isinstance(exc, ConflictError):
        status = 409
    return error_response(status, exc.code, exc.message, exc.details)


async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors: list[JsonValue] = [
        {"location": list(error["loc"]), "type": error["type"], "message": "Invalid value"}
        for error in exc.errors()
    ]
    return error_response(422, "VALIDATION_ERROR", "Request validation failed", {"errors": errors})


async def handle_http_error(request: Request, exc: HTTPException) -> JSONResponse:
    code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return error_response(exc.status_code, code, message, headers=exc.headers)


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # Preserve diagnostic stack locations without exception text, locals, or request data.
    frames = traceback.extract_tb(exc.__traceback__)
    locations = " -> ".join(f"{frame.filename}:{frame.lineno} ({frame.name})" for frame in frames)
    logger.error("Unhandled %s at %s", type(exc).__name__, locations)
    response = error_response(500, "INTERNAL_SERVER_ERROR", "An unexpected server error occurred")
    # Starlette's unexpected-error handler runs outside its CORS middleware.
    origin = request.headers.get("origin")
    if origin == get_settings(request).frontend_origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers.add_vary_header("Origin")
    return response


def register_exception_handlers(application: FastAPI) -> None:
    application.add_exception_handler(AppError, handle_app_error)
    application.add_exception_handler(RequestValidationError, handle_validation_error)
    application.add_exception_handler(HTTPException, handle_http_error)
    application.add_exception_handler(Exception, handle_unexpected_error)
