from uuid import UUID

from sqlmodel import Session, col, delete, func, or_, select

from app.core.errors import ConflictError, NotFoundError
from app.core.models import Tag, Torrent, TorrentFile, TorrentMetadataStatus, User, Video, VideoTag, utcnow
from app.storage.blob_store import BlobStore
from app.torrents.provider import TorrentMetadataProvider
from app.torrents.repository import get_or_create_torrent
from app.torrents.service import process_torrent_metadata
from app.videos.schemas import VideoCreate, VideoListResponse, VideoUpdate, video_to_detail, video_to_summary
from app.videos.validation import normalize_info_hash, validate_rating


def _load_tags(session: Session, tag_ids: list[UUID]) -> list[Tag]:
    if not tag_ids:
        return []
    tags = list(session.exec(select(Tag).where(col(Tag.id).in_(tag_ids))).all())
    if len(tags) != len(set(tag_ids)):
        raise NotFoundError("One or more tags were not found")
    return tags


def _video_tags(session: Session, video_id: UUID) -> list[Tag]:
    return list(session.exec(select(Tag).join(VideoTag).where(col(VideoTag.video_id) == video_id)).all())


def _video_files(session: Session, torrent_id: UUID) -> list[TorrentFile]:
    return list(
        session.exec(
            select(TorrentFile).where(col(TorrentFile.torrent_id) == torrent_id).order_by(col(TorrentFile.position))
        ).all()
    )


def _video_torrent(session: Session, video: Video) -> Torrent:
    torrent = session.get(Torrent, video.torrent_id)
    if torrent is None:
        raise NotFoundError("Torrent was not found")
    return torrent


def _replace_video_tags(session: Session, video: Video, tags: list[Tag]) -> None:
    session.exec(delete(VideoTag).where(col(VideoTag.video_id) == video.id))
    for tag in tags:
        session.add(VideoTag(video_id=video.id, tag_id=tag.id))


def create_video(
    session: Session,
    user: User,
    payload: VideoCreate,
    provider: TorrentMetadataProvider,
    blob_store: BlobStore,
):
    info_hash = normalize_info_hash(payload.info_hash)
    validate_rating(payload.rating)
    torrent, created = get_or_create_torrent(session, info_hash)
    existing = session.exec(select(Video).where(Video.user_id == user.id, Video.torrent_id == torrent.id)).first()
    if existing:
        raise ConflictError("This video is already in your collection")
    video = Video(
        user_id=user.id,
        torrent_id=torrent.id,
        title=payload.title,
        description=payload.description,
        rating=payload.rating,
    )
    session.add(video)
    session.commit()
    session.refresh(video)
    _replace_video_tags(session, video, _load_tags(session, payload.tag_ids))
    session.commit()
    if created or torrent.metadata_status in {TorrentMetadataStatus.PENDING, TorrentMetadataStatus.FAILED}:
        process_torrent_metadata(session, torrent, provider, blob_store)
    session.refresh(video)
    return video_to_detail(
        video, _video_torrent(session, video), _video_tags(session, video.id), _video_files(session, video.torrent_id)
    )


def update_video(session: Session, user: User, video_id: UUID, payload: VideoUpdate):
    video = session.exec(select(Video).where(Video.id == video_id, Video.user_id == user.id)).first()
    if not video:
        raise NotFoundError("Video was not found")
    if payload.title is not None:
        video.title = payload.title
    if payload.description is not None:
        video.description = payload.description
    if payload.rating is not None:
        video.rating = validate_rating(payload.rating)
    if payload.tag_ids is not None:
        _replace_video_tags(session, video, _load_tags(session, payload.tag_ids))
    video.updated_at = utcnow()
    session.add(video)
    session.commit()
    session.refresh(video)
    return video_to_detail(
        video, _video_torrent(session, video), _video_tags(session, video.id), _video_files(session, video.torrent_id)
    )


def get_video(session: Session, user: User, video_id: UUID):
    video = session.exec(select(Video).where(Video.id == video_id, Video.user_id == user.id)).first()
    if not video:
        raise NotFoundError("Video was not found")
    return video_to_detail(
        video, _video_torrent(session, video), _video_tags(session, video.id), _video_files(session, video.torrent_id)
    )


def build_video_search_statement(
    user_id: UUID,
    q: str | None,
    rating: int | None,
    status: TorrentMetadataStatus | None,
):
    statement = select(Video).where(Video.user_id == user_id)
    joined_torrent = False
    if rating is not None:
        statement = statement.where(Video.rating == rating)
    if status is not None:
        statement = statement.join(Torrent).where(Torrent.metadata_status == status)
        joined_torrent = True
    if q:
        like = f"%{q.lower()}%"
        if not joined_torrent:
            statement = statement.join(Torrent)
        statement = statement.where(
            or_(
                func.lower(Video.title).like(like),
                func.lower(Video.description).like(like),
                func.lower(Torrent.name).like(like),
                func.lower(Torrent.info_hash).like(like),
            )
        )
    return statement.order_by(col(Video.created_at).desc(), col(Video.id).desc())


def search_videos(
    session: Session,
    user: User,
    q: str | None,
    tag: str | None,
    rating: int | None,
    status: TorrentMetadataStatus | None,
    limit: int,
    offset: int,
) -> VideoListResponse:
    statement = build_video_search_statement(user.id, q, rating, status)
    videos = list(session.exec(statement.offset(offset).limit(limit)).all())
    if tag:
        videos = [
            video for video in videos if any(t.name.lower() == tag.lower() for t in _video_tags(session, video.id))
        ]
    total = len(videos)
    return VideoListResponse(
        items=[
            video_to_summary(video, _video_torrent(session, video), _video_tags(session, video.id)) for video in videos
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
