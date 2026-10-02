from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedMixin, IdentityMixin


class Collection(IdentityMixin, CreatedMixin, Base):
    __tablename__ = "collections"
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)


class CollectionVideo(Base):
    __tablename__ = "collection_videos"
    collection_id: Mapped[str] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True
    )
    video_id: Mapped[str] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class Tag(IdentityMixin, Base):
    __tablename__ = "tags"
    name: Mapped[str] = mapped_column(String(255), unique=True)


class VideoTag(Base):
    __tablename__ = "video_tags"
    video_id: Mapped[str] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[str] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True, index=True
    )
