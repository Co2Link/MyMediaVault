from typing import Annotated

from fastapi import Depends, Header, Security
from fastapi_azure_auth import SingleTenantAzureAuthorizationCodeBearer
from fastapi_azure_auth.user import User as EntraUser
from sqlmodel import Session, select

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.errors import ForbiddenError
from app.core.models import User

_initial_settings = get_settings()


def _build_azure_scheme(settings: Settings) -> SingleTenantAzureAuthorizationCodeBearer:
    return SingleTenantAzureAuthorizationCodeBearer(
        app_client_id=settings.entra_client_id or "",
        tenant_id=settings.entra_tenant_id or "",
        scopes=settings.entra_scopes,
        auto_error=False,
        openapi_authorization_url=settings.entra_authorization_url,
        openapi_token_url=settings.entra_token_url,
    )


azure_scheme = _build_azure_scheme(_initial_settings)
_azure_scheme_key: tuple[str, str, str] | None = (
    _initial_settings.entra_tenant_id or "",
    _initial_settings.entra_client_id or "",
    _initial_settings.entra_scope_name,
)


def configure_azure_scheme(settings: Settings) -> SingleTenantAzureAuthorizationCodeBearer:
    if not settings.production_auth_configured:
        raise ForbiddenError("Production authentication is not configured")

    global _azure_scheme_key
    scheme_key = (settings.entra_tenant_id or "", settings.entra_client_id or "", settings.entra_scope_name)
    if _azure_scheme_key != scheme_key:
        configured_scheme = _build_azure_scheme(settings)
        azure_scheme.__dict__.clear()
        azure_scheme.__dict__.update(configured_scheme.__dict__)
        _azure_scheme_key = scheme_key
    return azure_scheme


async def load_azure_openid_config(settings: Settings) -> None:
    if settings.environment != "test" and settings.production_auth_configured:
        await configure_azure_scheme(settings).openid_config.load_config()


def _is_entra_admin(entra_user: EntraUser, settings: Settings) -> bool:
    if entra_user.oid and entra_user.oid in settings.admin_object_ids:
        return True
    return any(role in settings.admin_role_names for role in entra_user.roles)


def _upsert_user(session: Session, subject: str, display_name: str | None, email: str | None, is_admin: bool) -> User:
    user = session.exec(select(User).where(User.external_subject == subject)).first()
    if user is None:
        user = User(
            external_subject=subject,
            display_name=display_name,
            email=email,
            is_admin=is_admin,
        )
        session.add(user)
    else:
        user.display_name = display_name or user.display_name
        user.email = email or user.email
        user.is_admin = is_admin
        session.add(user)
    session.commit()
    session.refresh(user)
    return user


async def get_current_user(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    entra_user: Annotated[EntraUser | None, Security(azure_scheme)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    configure_azure_scheme(settings)

    if not authorization:
        raise ForbiddenError("Authentication is required")

    if entra_user is None:
        raise ForbiddenError("Authentication token is invalid")
    subject = entra_user.oid or entra_user.sub
    return _upsert_user(
        session,
        subject=subject,
        display_name=entra_user.name,
        email=entra_user.preferred_username or entra_user.email,
        is_admin=_is_entra_admin(entra_user, settings),
    )
