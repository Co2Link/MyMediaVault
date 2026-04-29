from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class TorrentMetadataStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TorrentJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class VideoTag(SQLModel, table=True):
    __tablename__ = "video_tags"
    __table_args__ = (UniqueConstraint("video_id", "tag_id", name="uq_video_tags_video_tag"),)

    video_id: UUID = Field(foreign_key="videos.id", primary_key=True)
    tag_id: UUID = Field(foreign_key="tags.id", primary_key=True)
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    external_subject: str = Field(max_length=255, index=True, unique=True)
    display_name: str | None = None
    email: str | None = None
    is_admin: bool = False
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False))


class Torrent(SQLModel, table=True):
    __tablename__ = "torrents"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    info_hash: str = Field(max_length=64, index=True, unique=True)
    name: str | None = Field(default=None, max_length=512, index=True)
    size_bytes: int | None = None
    raw_blob_key: str | None = None
    metadata_status: TorrentMetadataStatus = Field(default=TorrentMetadataStatus.PENDING, max_length=32, index=True)
    metadata_error: str | None = None
    metadata_attempts: int = 0
    metadata_last_attempt_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False))


class TorrentFile(SQLModel, table=True):
    __tablename__ = "torrent_files"
    __table_args__ = (UniqueConstraint("torrent_id", "position", name="uq_torrent_files_torrent_position"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    torrent_id: UUID = Field(foreign_key="torrents.id", index=True)
    path: str
    size_bytes: int
    position: int


class Tag(SQLModel, table=True):
    __tablename__ = "tags"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=128, index=True, unique=True)
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False))


class Video(SQLModel, table=True):
    __tablename__ = "videos"
    __table_args__ = (UniqueConstraint("user_id", "torrent_id", name="uq_videos_user_torrent"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    torrent_id: UUID = Field(foreign_key="torrents.id", index=True)
    title: str | None = Field(default=None, max_length=512, index=True)
    description: str | None = None
    rating: int | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False))


class TorrentProcessingJob(SQLModel, table=True):
    __tablename__ = "torrent_processing_jobs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    torrent_id: UUID = Field(foreign_key="torrents.id", index=True)
    status: TorrentJobStatus = Field(default=TorrentJobStatus.QUEUED, max_length=32, index=True)
    error: str | None = None
    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    finished_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False))
