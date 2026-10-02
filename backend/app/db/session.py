import sqlite3
from collections.abc import Iterator
from pathlib import Path

from fastapi import Request
from sqlalchemy import Engine, event
from sqlalchemy import create_engine as sqlalchemy_create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry, StaticPool

from app.core.config import REPOSITORY_ROOT, Settings


def resolve_database_url(settings: Settings) -> URL:
    url = make_url(settings.database_url)
    if url.database != ":memory:":
        database_path = (REPOSITORY_ROOT / Path(url.database or "")).resolve()
        url = url.set(database=database_path.as_posix())
    return url


def enable_foreign_keys(connection: sqlite3.Connection, record: ConnectionPoolEntry) -> None:
    previous = connection.autocommit
    connection.autocommit = True
    try:
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()
    finally:
        connection.autocommit = previous


def create_database_engine(settings: Settings) -> Engine:
    url = resolve_database_url(settings)
    options = {"poolclass": StaticPool} if url.database == ":memory:" else {}
    engine = sqlalchemy_create_engine(
        url,
        connect_args={"check_same_thread": False, "autocommit": False},
        **options,
    )
    event.listen(engine, "connect", enable_foreign_keys)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=True)


def get_session(request: Request) -> Iterator[Session]:
    """Request-owned session; caller owns commit, uncommitted work is rolled back."""
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        try:
            yield session
        finally:
            session.rollback()
