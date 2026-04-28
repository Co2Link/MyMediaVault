from uuid import UUID

from sqlmodel import Session, select

from app.core.errors import ConflictError, NotFoundError
from app.core.models import Tag, VideoTag, utcnow
from app.tags.schemas import TagCreate, TagRead, TagUpdate


def _normalize_name(name: str) -> str:
    normalized = " ".join(name.strip().split())
    if not normalized:
        raise ConflictError("Tag name is required")
    return normalized


def _to_read(tag: Tag) -> TagRead:
    return TagRead(id=tag.id, name=tag.name)


def list_tags(session: Session) -> list[TagRead]:
    return [_to_read(tag) for tag in session.exec(select(Tag).order_by(Tag.name)).all()]


def create_tag(session: Session, payload: TagCreate) -> TagRead:
    name = _normalize_name(payload.name)
    existing = session.exec(select(Tag).where(Tag.name == name)).first()
    if existing:
        raise ConflictError("Tag name already exists")
    tag = Tag(name=name)
    session.add(tag)
    session.commit()
    session.refresh(tag)
    return _to_read(tag)


def update_tag(session: Session, tag_id: UUID, payload: TagUpdate) -> TagRead:
    tag = session.get(Tag, tag_id)
    if not tag:
        raise NotFoundError("Tag was not found")
    name = _normalize_name(payload.name)
    existing = session.exec(select(Tag).where(Tag.name == name, Tag.id != tag_id)).first()
    if existing:
        raise ConflictError("Tag name already exists")
    tag.name = name
    tag.updated_at = utcnow()
    session.add(tag)
    session.commit()
    session.refresh(tag)
    return _to_read(tag)


def delete_tag(session: Session, tag_id: UUID) -> None:
    tag = session.get(Tag, tag_id)
    if not tag:
        raise NotFoundError("Tag was not found")
    for link in session.exec(select(VideoTag).where(VideoTag.tag_id == tag_id)).all():
        session.delete(link)
    session.delete(tag)
    session.commit()
