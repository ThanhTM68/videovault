import logging
from typing import Annotated

import pytest
from fastapi import FastAPI, HTTPException, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel, field_validator

from app.core.errors import AppError, ConflictError, NotFoundError
from app.schemas.errors import ErrorResponse


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (AppError("Operation failed", details={"reason": "test"}), 400),
        (NotFoundError("Item missing", details={"id": "123"}), 404),
        (ConflictError("Already exists", details={"ids": [1, 2]}), 409),
    ],
)
def test_domain_error_mapping(application: FastAPI, error: AppError, status: int) -> None:
    @application.get("/api/v1/test-error")
    def fail() -> None:
        raise error

    with TestClient(application) as client:
        response = client.get("/api/v1/test-error")
    assert response.status_code == status
    envelope = ErrorResponse.model_validate(response.json())
    assert envelope.error.code == error.code
    assert envelope.error.message == error.message
    assert envelope.error.details == error.details


def test_domain_details_are_not_shared() -> None:
    first = AppError("First")
    second = AppError("Second")
    first.details["reason"] = "first"
    assert second.details == {}


def test_request_validation_does_not_echo_input(application: FastAPI) -> None:
    @application.get("/api/v1/test-validation")
    def validate(count: Annotated[int, Query(gt=0)]) -> dict[str, int]:
        return {"count": count}

    with TestClient(application) as client:
        response = client.get("/api/v1/test-validation?count=private-token")
    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "details": {
                "errors": [
                    {
                        "location": ["query", "count"],
                        "type": "int_parsing",
                        "message": "Invalid value",
                    }
                ]
            },
        }
    }
    assert "private-token" not in response.text


class InvalidPayload(BaseModel):
    value: str

    @field_validator("value")
    @classmethod
    def reject(cls, value: str) -> str:
        raise ValueError(f"Private input: {value}")


@pytest.mark.parametrize("body", ['{"value":"private-token"}', '{"value":'])
def test_body_validation_is_sanitized(application: FastAPI, body: str) -> None:
    @application.post("/api/v1/test-body")
    def validate(payload: InvalidPayload) -> None:
        return None

    with TestClient(application) as client:
        response = client.post(
            "/api/v1/test-body", content=body, headers={"Content-Type": "application/json"}
        )
    assert response.status_code == 422
    assert ErrorResponse.model_validate(response.json()).error.code == "VALIDATION_ERROR"
    assert "private-token" not in response.text
    assert "Private input" not in response.text
    assert "ctx" not in response.text


def test_http_error_preserves_headers(application: FastAPI) -> None:
    @application.get("/api/v1/test-http")
    def fail() -> None:
        raise HTTPException(429, "Try later", headers={"Retry-After": "30"})

    with TestClient(application) as client:
        response = client.get("/api/v1/test-http")
    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"
    assert response.json()["error"] == {"code": "HTTP_ERROR", "message": "Try later", "details": {}}


def test_unexpected_errors_remain_visible_to_tests(application: FastAPI) -> None:
    @application.get("/api/v1/test-unexpected")
    def fail() -> None:
        raise RuntimeError("private-token")

    with TestClient(application) as client, pytest.raises(RuntimeError, match="private-token"):
        client.get("/api/v1/test-unexpected")


@pytest.mark.parametrize("origin", ["http://127.0.0.1:5173", "https://untrusted.example"])
def test_unexpected_error_response_and_logs_are_sanitized(
    application: FastAPI, caplog: pytest.LogCaptureFixture, origin: str
) -> None:
    @application.get("/api/v1/test-unexpected")
    def fail() -> None:
        raise RuntimeError("private-token")

    with caplog.at_level(logging.ERROR, logger="app.api.error_handlers"):
        with TestClient(application, raise_server_exceptions=False) as client:
            response = client.get("/api/v1/test-unexpected", headers={"Origin": origin})
    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected server error occurred",
            "details": {},
        }
    }
    assert "private-token" not in response.text
    assert "Traceback" not in response.text
    assert "private-token" not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "test_errors.py" in caplog.text
    if origin == application.state.settings.frontend_origin:
        assert response.headers["access-control-allow-origin"] == origin
        assert response.headers["vary"] == "Origin"
    else:
        assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-credentials" not in response.headers
