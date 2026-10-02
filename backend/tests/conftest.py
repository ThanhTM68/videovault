import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.application import create_app
from app.core.config import Settings
from app.core.errors import MissingMediaToolError
from app.db.session import create_database_engine, create_session_factory
from app.services.media.probe import require_tool


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
        monkeypatch.delenv(name.lower(), raising=False)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite:///" + (tmp_path / "test.db").as_posix(),
    )


@pytest.fixture
def application(settings: Settings) -> FastAPI:
    # Foundation tests deliberately exercise process-only health without a migrated DB.
    # Queue integration tests opt into the real lifecycle on migrated temporary files.
    return create_app(settings, start_workers=False)


@pytest.fixture
def client(application: FastAPI) -> Iterator[TestClient]:
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def alembic_config() -> Config:
    return Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))


@pytest.fixture
def db_engine(settings: Settings, alembic_config: Config) -> Iterator[Engine]:
    engine = create_database_engine(settings)
    try:
        with engine.begin() as connection:
            alembic_config.attributes["connection"] = connection
            command.upgrade(alembic_config, "head")
        alembic_config.attributes.pop("connection")
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    with create_session_factory(db_engine)() as session:
        yield session
        session.rollback()


@pytest.fixture
def local_media(tmp_path: Path) -> Path:
    """Tiny generated MP4; no committed binaries and no remote platform traffic."""
    try:
        ffmpeg = require_tool("ffmpeg")
        require_tool("ffprobe")
    except MissingMediaToolError:
        pytest.skip("Local integration requires globally installed ffmpeg and ffprobe")
    path = tmp_path / "sample.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x48:r=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=400:sample_rate=44100",
            "-t",
            "0.3",
            "-c:v",
            "mpeg4",
            "-c:a",
            "aac",
            "-threads",
            "1",
            "-y",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=30,
        shell=False,
    )
    return path
