import asyncio
from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

from app.auth.dependencies import _is_entra_admin, get_current_user
from app.core.config import Settings
from app.auth.authorization import require_admin
from app.core.errors import ForbiddenError
from app.core.models import User


def test_require_admin_allows_admin() -> None:
    user = User(external_subject="admin", is_admin=True)
    assert require_admin(user) is user


def test_require_admin_rejects_standard_user() -> None:
    with pytest.raises(ForbiddenError):
        require_admin(User(external_subject="user", is_admin=False))


def test_get_current_user_requires_authorization_header(session: Session) -> None:
    settings = Settings(entra_tenant_id="tenant", entra_client_id="backend-client-id")

    with pytest.raises(ForbiddenError, match="Authentication is required"):
        asyncio.run(get_current_user(session=session, settings=settings, entra_user=None, authorization=None))


def test_get_current_user_rejects_invalid_token(session: Session) -> None:
    settings = Settings(entra_tenant_id="tenant", entra_client_id="backend-client-id")

    with pytest.raises(ForbiddenError, match="Authentication token is invalid"):
        asyncio.run(get_current_user(session=session, settings=settings, entra_user=None, authorization="Bearer invalid"))


def test_get_current_user_upserts_entra_user(session: Session) -> None:
    settings = Settings(entra_tenant_id="tenant", entra_client_id="backend-client-id")
    entra_user = SimpleNamespace(
        oid="entra-oid-1",
        sub="entra-sub-1",
        name="Entra User",
        preferred_username="entra.user@example.com",
        email=None,
        roles=[],
    )

    resolved_user = asyncio.run(
        get_current_user(
            session=session,
            settings=settings,
            entra_user=entra_user,
            authorization="Bearer valid",
        )
    )

    assert resolved_user.external_subject == "entra-oid-1"
    assert resolved_user.display_name == "Entra User"
    assert resolved_user.email == "entra.user@example.com"
    assert resolved_user.is_admin is False
    persisted_user = session.exec(select(User).where(User.external_subject == "entra-oid-1")).one()
    assert persisted_user.id == resolved_user.id


def test_entra_admin_mapping_supports_object_ids_and_roles() -> None:
    by_object_id = SimpleNamespace(oid="admin-oid", roles=[])
    by_role = SimpleNamespace(oid="user-oid", roles=["MyMediaVault.Admin"])

    assert _is_entra_admin(by_object_id, Settings(admin_object_ids=["admin-oid"])) is True
    assert _is_entra_admin(by_role, Settings(admin_role_names=["MyMediaVault.Admin"])) is True
