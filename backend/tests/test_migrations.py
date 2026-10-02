import os
import subprocess
import sys
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect

from app.core.config import Settings
from app.db.base import Base
from app.db.session import create_database_engine

EXPECTED_TABLES = {
    "creators",
    "videos",
    "downloads",
    "media_files",
    "jobs",
    "collections",
    "collection_videos",
    "tags",
    "video_tags",
    "storage_accounts",
}


def test_fresh_migration_and_metadata_parity(db_engine: Engine) -> None:
    inspector = inspect(db_engine)
    assert set(inspector.get_table_names()) == EXPECTED_TABLES | {"alembic_version"}
    assert inspector.get_pk_constraint("collection_videos")["constrained_columns"] == [
        "collection_id",
        "video_id",
    ]
    assert inspector.get_pk_constraint("video_tags")["constrained_columns"] == [
        "video_id",
        "tag_id",
    ]
    assert inspector.get_unique_constraints("videos")[0]["column_names"] == [
        "platform",
        "platform_video_id",
    ]
    with db_engine.connect() as connection:
        assert (
            connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
            == "0001_v1"
        )
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_downgrade_and_reupgrade(db_engine: Engine, alembic_config: Config) -> None:
    with db_engine.begin() as connection:
        alembic_config.attributes["connection"] = connection
        command.downgrade(alembic_config, "base")
    assert set(inspect(db_engine).get_table_names()) == {"alembic_version"}
    with db_engine.begin() as connection:
        alembic_config.attributes["connection"] = connection
        command.upgrade(alembic_config, "head")
    assert set(inspect(db_engine).get_table_names()) == EXPECTED_TABLES | {"alembic_version"}


def test_actual_fk_and_index_contract(db_engine: Engine) -> None:
    inspector = inspect(db_engine)
    expected = {
        "videos": {"creator_id": "SET NULL"},
        "downloads": {"video_id": "RESTRICT", "job_id": "SET NULL"},
        "media_files": {"video_id": "RESTRICT", "download_id": "SET NULL"},
        "collection_videos": {"collection_id": "CASCADE", "video_id": "CASCADE"},
        "video_tags": {"video_id": "CASCADE", "tag_id": "CASCADE"},
    }
    for table, columns in expected.items():
        assert {
            fk["constrained_columns"][0]: fk["options"]["ondelete"]
            for fk in inspector.get_foreign_keys(table)
        } == columns
    assert {index["name"] for index in inspector.get_indexes("downloads")} == {
        "ix_downloads_video_id",
        "ix_downloads_job_id",
    }
    for table in ("creators", "videos", "downloads", "jobs", "media_files", "storage_accounts"):
        assert inspector.get_check_constraints(table)


def test_migration_import_does_not_start_application(db_engine: Engine) -> None:
    assert "app.main" not in sys.modules


def test_alembic_cli_up_down_up_and_check_from_other_directory(
    tmp_path: Path, settings: Settings, alembic_config: Config
) -> None:
    env = os.environ.copy()
    env.update({name.upper(): str(value) for name, value in settings.model_dump().items()})
    for arguments in (["upgrade", "head"], ["downgrade", "base"], ["upgrade", "head"], ["check"]):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", alembic_config.config_file_name, *arguments],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.returncode == 0
    engine = create_database_engine(settings)
    try:
        assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES | {"alembic_version"}
    finally:
        engine.dispose()


def test_offline_migration_does_not_create_database(
    tmp_path: Path, settings: Settings, alembic_config: Config
) -> None:
    env = os.environ.copy()
    env.update({name.upper(): str(value) for name, value in settings.model_dump().items()})
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            alembic_config.config_file_name,
            "upgrade",
            "head",
            "--sql",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "CREATE TABLE videos" in result.stdout
    assert "0001_v1" in result.stdout
    assert not (tmp_path / "test.db").exists()
