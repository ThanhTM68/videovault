from pathlib import Path
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.application import create_app
from app.core.config import REPOSITORY_ROOT, Settings
from app.db.session import (
    create_database_engine,
    create_session_factory,
    get_session,
    resolve_database_url,
)
from app.models import Video
from app.repositories.videos import VideoRepository
from tests.factories import make_video


def test_database_path_resolution_is_independent_of_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    default = Settings(_env_file=None)
    assert Path(resolve_database_url(default).database) == REPOSITORY_ROOT / "data/videovault.db"
    absolute = tmp_path / "database with spaces.db"
    configured = Settings(_env_file=None, database_url="sqlite:///" + absolute.as_posix())
    assert Path(resolve_database_url(configured).database) == absolute
    engine = create_database_engine(configured)
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    finally:
        engine.dispose()
    assert absolute.exists()
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("commit", [False, True])
def test_request_session_does_not_auto_commit(
    application: FastAPI, db_engine: Engine, commit: bool
) -> None:
    @application.post("/api/v1/test-session")
    def write(session: Annotated[Session, Depends(get_session)]) -> dict[str, str]:
        video = VideoRepository(session).add(make_video())
        if commit:
            session.commit()
        return {"id": video.id}

    with TestClient(application) as client:
        response = client.post("/api/v1/test-session")
        assert response.status_code == 200
        assert application.state.engine.pool.checkedout() == 0
    with create_session_factory(db_engine)() as observer:
        persisted = observer.scalars(select(Video)).all()
        assert len(persisted) == (1 if commit else 0)


@pytest.mark.parametrize("failure", ["unexpected", "integrity"])
def test_failed_request_rolls_back_and_releases_session(
    application: FastAPI, db_engine: Engine, failure: str
) -> None:
    @application.post("/api/v1/test-failed-session")
    def fail(session: Annotated[Session, Depends(get_session)]) -> None:
        repository = VideoRepository(session)
        repository.add(make_video())
        if failure == "integrity":
            repository.add(make_video())
        raise RuntimeError("test failure")

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.post("/api/v1/test-failed-session")
        assert response.status_code == 500
        assert application.state.engine.pool.checkedout() == 0
        assert client.get("/api/v1/health").status_code == 200
    with create_session_factory(db_engine)() as observer:
        assert observer.scalars(select(Video)).all() == []
        VideoRepository(observer).add(make_video("new-request"))
        observer.commit()


def test_engine_is_disposed_on_shutdown(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = create_app(settings)
    engine = application.state.engine
    original_dispose = engine.dispose
    disposed: list[bool] = []

    def dispose() -> None:
        original_dispose()
        disposed.append(True)

    monkeypatch.setattr(engine, "dispose", dispose)
    with TestClient(application) as client:
        assert client.get("/api/v1/health").status_code == 200
    assert disposed == [True]
