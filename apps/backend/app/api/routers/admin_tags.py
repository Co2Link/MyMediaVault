from uuid import UUID

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUserDep, SessionDep
from app.auth.authorization import require_admin
from app.tags.schemas import TagCreate, TagRead, TagUpdate
from app.tags.service import create_tag, delete_tag, list_tags, update_tag

router = APIRouter(prefix="/admin/tags", tags=["admin-tags"])


@router.get("", response_model=list[TagRead])
def list_tags_route(session: SessionDep, current_user: CurrentUserDep) -> list[TagRead]:
    require_admin(current_user)
    return list_tags(session)


@router.post("", response_model=TagRead, status_code=status.HTTP_201_CREATED)
def create_tag_route(payload: TagCreate, session: SessionDep, current_user: CurrentUserDep) -> TagRead:
    require_admin(current_user)
    return create_tag(session, payload)


@router.patch("/{tag_id}", response_model=TagRead)
def update_tag_route(tag_id: UUID, payload: TagUpdate, session: SessionDep, current_user: CurrentUserDep) -> TagRead:
    require_admin(current_user)
    return update_tag(session, tag_id, payload)


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag_route(tag_id: UUID, session: SessionDep, current_user: CurrentUserDep) -> Response:
    require_admin(current_user)
    delete_tag(session, tag_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
