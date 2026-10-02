from pathlib import Path

import pytest
from pydantic import ValidationError

from app.application import create_app
from app.core.config import REPOSITORY_ROOT, Settings


def test_dotenv_loading_and_environment_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "APP_PORT=8123\nAPP_ENV=test\nDATABASE_URL=sqlite:///example.db\nUNUSED_FUTURE_KEY=unused\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("APP_PORT", "8124")

    settings = Settings(_env_file=dotenv)

    assert settings.app_env == "test"
    assert settings.app_port == 8124
    assert settings.database_url == "sqlite:///example.db"


@pytest.mark.parametrize("port", ["0", "65536", "invalid"])
def test_invalid_port_is_rejected(port: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_PORT", port)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_development_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_env == "development"
    assert settings.app_host == "127.0.0.1"
    assert settings.app_port == 8000
    assert settings.database_url == "sqlite:///./data/videovault.db"
    assert settings.local_storage_root == REPOSITORY_ROOT / "data/downloads"
    assert settings.temp_storage_root == REPOSITORY_ROOT / "data/temp"
    assert settings.thumbnail_storage_root == REPOSITORY_ROOT / "data/thumbnails"
    assert settings.download_max_height == 1080
    assert settings.download_concurrency == 3
    assert settings.frontend_origin == "http://127.0.0.1:5173"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("APP_ENV", "invalid"),
        ("APP_HOST", ""),
        ("APP_HOST", "http://localhost"),
        ("APP_HOST", "999.999.999.999"),
        ("APP_HOST", "-invalid"),
        ("APP_HOST", "invalid..host"),
        ("DATABASE_URL", "postgresql://private:secret@example/db"),
        ("DATABASE_URL", "sqlite:///"),
        ("DATABASE_URL", "sqlite:///file:test.db"),
        ("DATABASE_URL", "sqlite:///test.db?uri=true"),
        ("DOWNLOAD_MAX_HEIGHT", "0"),
        ("DOWNLOAD_MAX_HEIGHT", "1081"),
        ("DOWNLOAD_CONCURRENCY", "0"),
        ("LOCAL_STORAGE_ROOT", ""),
        ("TEMP_STORAGE_ROOT", " "),
        ("THUMBNAIL_STORAGE_ROOT", ""),
        ("FRONTEND_ORIGIN", "*"),
        ("FRONTEND_ORIGIN", "ftp://example.com"),
        ("FRONTEND_ORIGIN", "http://private:secret@example.com"),
        ("FRONTEND_ORIGIN", "http://example.com/path"),
        ("FRONTEND_ORIGIN", "http://example.com?query=secret"),
        ("FRONTEND_ORIGIN", "http://example.com#fragment"),
    ],
)
def test_invalid_configuration(name: str, value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)
    assert name.lower() in str(error.value)
    assert "secret" not in str(error.value)


def test_environment_overrides_and_normalized_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_HOST", "localhost")
    monkeypatch.setenv("DOWNLOAD_MAX_HEIGHT", "720")
    monkeypatch.setenv("DOWNLOAD_CONCURRENCY", "2")
    monkeypatch.setenv("LOCAL_STORAGE_ROOT", "./data/../data/custom")
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:5173/")
    settings = Settings(_env_file=None)
    assert settings.app_host == "localhost"
    assert settings.download_max_height == 720
    assert settings.download_concurrency == 2
    assert settings.local_storage_root == REPOSITORY_ROOT / "data/custom"
    assert settings.frontend_origin == "http://localhost:5173"


def test_absolute_storage_path_is_preserved(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, local_storage_root=tmp_path)
    assert settings.local_storage_root == tmp_path.resolve()


def test_relative_paths_do_not_depend_on_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings(_env_file=None, temp_storage_root="data/scratch")
    assert settings.temp_storage_root == REPOSITORY_ROOT / "data/scratch"


def test_startup_does_not_create_storage_or_database(tmp_path: Path) -> None:
    storage = tmp_path / "downloads"
    database = tmp_path / "videovault.db"
    settings = Settings(
        _env_file=None,
        app_env="test",
        local_storage_root=storage,
        database_url=f"sqlite:///{database.as_posix()}",
    )
    create_app(settings)
    assert not storage.exists()
    assert not database.exists()


def test_environment_example_is_valid() -> None:
    settings = Settings(_env_file=REPOSITORY_ROOT / ".env.example")
    assert settings.app_env == "development"
    assert settings.frontend_origin == "http://127.0.0.1:5173"


def test_database_url_is_excluded_from_settings_repr() -> None:
    settings = Settings(_env_file=None, database_url="sqlite:///private-token.db")
    assert "private-token" not in repr(settings)


def test_factory_rejects_invalid_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_PORT", "0")
    with pytest.raises(ValidationError):
        create_app()
