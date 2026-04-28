from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.models import TorrentMetadataStatus


class TagRead(BaseModel):
    id: UUID
    name: str


class TorrentFileRead(BaseModel):
    path: str
    size_bytes: int = Field(alias="sizeBytes")

    model_config = {"populate_by_name": True}


class VideoCreate(BaseModel):
    info_hash: str = Field(alias="infoHash")
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    rating: int | None = Field(default=None, ge=1, le=5)
    tag_ids: list[UUID] = Field(default_factory=list, alias="tagIds")

    model_config = {"populate_by_name": True}


class VideoUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    rating: int | None = Field(default=None, ge=1, le=5)
    tag_ids: list[UUID] | None = Field(default=None, alias="tagIds")

    model_config = {"populate_by_name": True}


class VideoSummary(BaseModel):
    id: UUID
    display_title: str | None = Field(alias="displayTitle")
    title: str | None = None
    rating: int | None = None
    info_hash: str = Field(alias="infoHash")
    torrent_name: str | None = Field(default=None, alias="torrentName")
    metadata_status: TorrentMetadataStatus = Field(alias="metadataStatus")
    tags: list[TagRead] = Field(default_factory=list)
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = {"populate_by_name": True}


class VideoDetail(VideoSummary):
    description: str | None = None
    size_bytes: int | None = Field(default=None, alias="sizeBytes")
    metadata_error: str | None = Field(default=None, alias="metadataError")
    files: list[TorrentFileRead] = Field(default_factory=list)


class VideoListResponse(BaseModel):
    items: list[VideoSummary]
    total: int
    limit: int
    offset: int


def video_to_summary(video, torrent, tags) -> VideoSummary:
    display_title = video.title or torrent.name
    return VideoSummary.model_validate(
        {
            "id": video.id,
            "display_title": display_title,
            "title": video.title,
            "rating": video.rating,
            "info_hash": torrent.info_hash,
            "torrent_name": torrent.name,
            "metadata_status": torrent.metadata_status,
            "tags": [TagRead(id=tag.id, name=tag.name) for tag in tags],
            "created_at": video.created_at,
            "updated_at": video.updated_at,
        }
    )


def video_to_detail(video, torrent, tags, files) -> VideoDetail:
    summary = video_to_summary(video, torrent, tags).model_dump(by_alias=True)
    return VideoDetail.model_validate(
        {
            **summary,
            "description": video.description,
            "size_bytes": torrent.size_bytes,
            "metadata_error": torrent.metadata_error,
            "files": [TorrentFileRead(path=file.path, sizeBytes=file.size_bytes) for file in files],
        }
    )
