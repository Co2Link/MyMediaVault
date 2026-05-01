from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUserDep, SessionDep
from app.core.config import Settings, get_settings
from app.core.models import TorrentMetadataStatus
from app.torrents.provider import FakeTorrentMetadataProvider, HttpTorrentMetadataProvider, TorrentMetadataProvider
from app.videos.schemas import VideoCreate, VideoDetail, VideoListResponse, VideoUpdate
from app.videos.service import create_video, get_video, search_videos, update_video

router = APIRouter(prefix="/videos", tags=["videos"])


def get_torrent_provider(settings: Annotated[Settings, Depends(get_settings)]) -> TorrentMetadataProvider:
    if settings.torrent_provider == "http":
        return HttpTorrentMetadataProvider(settings.torrent_resolver_urls, settings.torrent_fetch_timeout_seconds)
    return FakeTorrentMetadataProvider()


@router.post("", response_model=VideoDetail, status_code=status.HTTP_202_ACCEPTED)
def create_video_route(
    payload: VideoCreate,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> VideoDetail:
    return create_video(session, current_user, payload)


@router.get("", response_model=VideoListResponse)
def search_videos_route(
    session: SessionDep,
    current_user: CurrentUserDep,
    q: str | None = None,
    tag: str | None = None,
    rating: Annotated[int | None, Query(ge=1, le=5)] = None,
    status_filter: Annotated[TorrentMetadataStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> VideoListResponse:
    return search_videos(session, current_user, q, tag, rating, status_filter, limit, offset)


@router.get("/{video_id}", response_model=VideoDetail)
def get_video_route(video_id: UUID, session: SessionDep, current_user: CurrentUserDep) -> VideoDetail:
    return get_video(session, current_user, video_id)


@router.patch("/{video_id}", response_model=VideoDetail)
def update_video_route(
    video_id: UUID,
    payload: VideoUpdate,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> VideoDetail:
    return update_video(session, current_user, video_id, payload)
