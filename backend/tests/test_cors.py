from fastapi.testclient import TestClient

from app.application import create_app
from app.core.config import Settings


def test_configured_origin_is_allowed() -> None:
    origin = "http://localhost:5173"
    application = create_app(Settings(_env_file=None, app_env="test", frontend_origin=origin))
    with TestClient(application) as client:
        response = client.get("/api/v1/health", headers={"Origin": origin})
        preflight = client.options(
            "/api/v1/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        error = client.get("/api/v1/missing", headers={"Origin": origin})
    assert response.headers["access-control-allow-origin"] == origin
    assert "access-control-allow-credentials" not in response.headers
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    assert error.headers["access-control-allow-origin"] == origin


def test_unconfigured_origin_is_rejected(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Origin": "https://untrusted.example"})
    preflight = client.options(
        "/api/v1/health",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in response.headers
    assert preflight.status_code == 400
    assert "access-control-allow-origin" not in preflight.headers
