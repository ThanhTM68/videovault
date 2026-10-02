from alembic import context
from sqlalchemy import Connection

from app import models  # noqa: F401 -- register the complete V1 metadata
from app.core.config import Settings
from app.db.base import Base
from app.db.session import create_database_engine, resolve_database_url
from app.db.types import StorageConfig, UTCDateTime

config = context.config
target_metadata = Base.metadata


def render_item(item_type: str, obj: object, autogen_context: object) -> str | bool:
    # Revisions contain ordinary SQL storage types, independent of current model code.
    if item_type == "type":
        if isinstance(obj, UTCDateTime):
            return "sa.DateTime()"
        if isinstance(obj, StorageConfig):
            return "sa.JSON()"
    return False


def configure_connection(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=True,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Tests can supply a connection, avoiding any developer .env/database access.
    connection = config.attributes.get("connection")
    if connection is not None:
        configure_connection(connection)
        return
    engine = create_database_engine(Settings())
    try:
        with engine.begin() as connection:
            configure_connection(connection)
    finally:
        engine.dispose()


def run_migrations_offline() -> None:
    context.configure(
        url=resolve_database_url(Settings()),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
