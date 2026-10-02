from datetime import date, datetime
from typing import TYPE_CHECKING

from pydantic import JsonValue
from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedMixin, IdentityMixin, utc_now
from app.db.types import UTCDateTime
from app.models.enums import Platform, enum_column

if TYPE_CHECKING:
    from app.models.download import Download, MediaFile


class Creator(IdentityMixin, CreatedMixin, Base):
    __tablename__ = "creators"
    __table_args__ = (UniqueConstraint("platform", "platform_creator_id"),)

    platform: Mapped[Platform] = mapped_column(enum_column(Platform, "platform"))
    platform_creator_id: Mapped[str | None] = mapped_column(String(255))
    handle: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)
    videos: Mapped[list["Video"]] = relationship(back_populates="creator", passive_deletes="all")


class Video(IdentityMixin, Base):
    __tablename__ = "videos"
    __table_args__ = (
        UniqueConstraint("platform", "platform_video_id"),
        CheckConstraint("length(trim(platform_video_id)) > 0", name="video_identity_nonempty"),
        CheckConstraint("duration_seconds >= 0", name="duration_nonnegative"),
        CheckConstraint("view_count >= 0", name="views_nonnegative"),
        CheckConstraint("like_count >= 0", name="likes_nonnegative"),
        CheckConstraint("comment_count >= 0", name="comments_nonnegative"),
        CheckConstraint("width > 0 AND height > 0", name="dimensions_positive"),
        CheckConstraint("fps > 0", name="fps_positive"),
    )

    platform: Mapped[Platform] = mapped_column(enum_column(Platform, "platform"))
    platform_video_id: Mapped[str] = mapped_column(String(255))
    canonical_url: Mapped[str] = mapped_column(Text)
    creator_id: Mapped[str | None] = mapped_column(
        ForeignKey("creators.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    duration_seconds: Mapped[float | None]
    upload_date: Mapped[date | None] = mapped_column(Date)
    view_count: Mapped[int | None] = mapped_column(BigInteger)
    like_count: Mapped[int | None] = mapped_column(BigInteger)
    comment_count: Mapped[int | None] = mapped_column(BigInteger)
    width: Mapped[int | None]
    height: Mapped[int | None]
    fps: Mapped[float | None]
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, JsonValue]] = mapped_column(
        MutableDict.as_mutable(JSON), default=dict
    )
    discovered_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    creator: Mapped[Creator | None] = relationship(back_populates="videos")
    downloads: Mapped[list["Download"]] = relationship(
        back_populates="video", passive_deletes="all"
    )
    media_files: Mapped[list["MediaFile"]] = relationship(
        back_populates="video", passive_deletes="all"
    )
