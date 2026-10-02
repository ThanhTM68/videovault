from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_dotenv_loading_and_environment_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("APP_PORT=8123\nAPP_ENV=test\nDATABASE_URL=unused\n", encoding="utf-8")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("APP_PORT", "8124")

    settings = Settings(_env_file=dotenv)

    assert settings.app_env == "test"
    assert settings.app_port == 8124


@pytest.mark.parametrize("port", ["0", "65536", "invalid"])
def test_invalid_port_is_rejected(port: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_PORT", port)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
