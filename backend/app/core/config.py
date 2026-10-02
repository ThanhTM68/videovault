import re
from ipaddress import ip_address
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_host: str = Field(default="127.0.0.1", min_length=1, pattern=r"^[A-Za-z0-9.:_-]+$")
    app_port: int = Field(default=8000, ge=1, le=65535)
    database_url: str = Field(default="sqlite:///./data/videovault.db", repr=False)
    local_storage_root: Path = REPOSITORY_ROOT / "data/downloads"
    temp_storage_root: Path = REPOSITORY_ROOT / "data/temp"
    thumbnail_storage_root: Path = REPOSITORY_ROOT / "data/thumbnails"
    download_max_height: int = Field(default=1080, ge=1, le=1080)
    download_concurrency: int = Field(default=3, ge=1)
    frontend_origin: str = "http://127.0.0.1:5173"

    @field_validator("app_host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        try:
            ip_address(value)
        except ValueError:
            labels = value.split(".")
            if (
                len(value) > 253
                or re.fullmatch(r"[0-9.]+", value)
                or not all(
                    re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                    for label in labels
                )
            ):
                raise ValueError("APP_HOST must be an IP address or hostname") from None
        return value

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("sqlite:///") or not value.removeprefix("sqlite:///").strip():
            raise ValueError("DATABASE_URL must be a SQLite URL with a database path")
        return value

    @field_validator(
        "local_storage_root", "temp_storage_root", "thumbnail_storage_root", mode="before"
    )
    @classmethod
    def validate_storage_path(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            raise ValueError("Storage path must not be empty")
        return value

    @field_validator("local_storage_root", "temp_storage_root", "thumbnail_storage_root")
    @classmethod
    def normalize_storage_path(cls, value: Path) -> Path:
        return (REPOSITORY_ROOT / value).resolve()

    @field_validator("frontend_origin")
    @classmethod
    def validate_frontend_origin(cls, value: str) -> str:
        origin = AnyHttpUrl(value)
        if (
            origin.username is not None
            or origin.password is not None
            or origin.path not in (None, "/")
            or origin.query is not None
            or origin.fragment is not None
        ):
            raise ValueError(
                "FRONTEND_ORIGIN must be an HTTP(S) origin without credentials or a path"
            )
        return str(origin).rstrip("/")
