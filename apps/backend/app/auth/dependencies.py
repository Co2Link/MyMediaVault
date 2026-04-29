from typing import Annotated, Any, cast

from fastapi import Depends, Header, Security
from fastapi_azure_auth import SingleTenantAzureAuthorizationCodeBearer
from fastapi_azure_auth.auth import jwt
from fastapi_azure_auth.user import User as EntraUser
from jwt.types import Options
from sqlmodel import Session, select

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.errors import ForbiddenError
from app.core.models import User

_initial_settings = get_settings()


class MyMediaVaultAzureScheme(SingleTenantAzureAuthorizationCodeBearer):
    def __init__(self, *args: Any, accepted_audiences: list[str], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.accepted_audiences = accepted_audiences

    def validate(self, access_token: str, key: Any, iss: str, options: dict[str, Any]) -> dict[str, Any]:
        return dict(
            jwt.decode(
                access_token,
                key=key,
                algorithms=["RS256"],
                audience=self.accepted_audiences,
                issuer=iss,
                leeway=self.leeway,
                options=cast(Options, options),
            )
        )


def _authorization_url(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"


def _token_url(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"


def _accepted_audiences(client_id: str) -> list[str]:
    if not client_id:
        return []
    app_id_uri = client_id if client_id.startswith("api://") else f"api://{client_id}"
    return list(dict.fromkeys([client_id, app_id_uri]))


def _build_azure_scheme(settings: Settings) -> MyMediaVaultAzureScheme:
    tenant_id = settings.entra_tenant_id or ""
    client_id = settings.entra_client_id or ""
    return MyMediaVaultAzureScheme(
        accepted_audiences=_accepted_audiences(client_id),
        app_client_id=client_id,
        tenant_id=tenant_id,
        scopes={settings.entra_api_scope: "Access MyMediaVault"},
        auto_error=False,
        openapi_authorization_url=_authorization_url(tenant_id),
        openapi_token_url=_token_url(tenant_id),
    )


_azure_scheme: MyMediaVaultAzureScheme = _build_azure_scheme(_initial_settings)
_azure_scheme_key: tuple[str, str, str] | None = (
    _initial_settings.entra_tenant_id or "",
    _initial_settings.entra_client_id or "",
    _initial_settings.entra_api_scope,
)


def _test_subject(x_test_user: str | None) -> str:
    return x_test_user or "test-user-1"


def _is_admin_subject(subject: str, x_test_admin: str | None) -> bool:
    return subject == "admin" or x_test_admin == "true"


def get_azure_scheme(settings: Settings) -> MyMediaVaultAzureScheme:
    if not settings.production_auth_configured:
        raise ForbiddenError("Production authentication is not configured")

    global _azure_scheme, _azure_scheme_key
    scheme_key = (settings.entra_tenant_id or "", settings.entra_client_id or "", settings.entra_api_scope)
    if _azure_scheme_key != scheme_key:
        _azure_scheme = _build_azure_scheme(settings)
        _azure_scheme_key = scheme_key
    return _azure_scheme


async def load_azure_openid_config(settings: Settings) -> None:
    if settings.production_auth_configured:
        await get_azure_scheme(settings).openid_config.load_config()


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
    entra_user: Annotated[EntraUser | None, Security(_azure_scheme)],
    authorization: Annotated[str | None, Header()] = None,
    x_test_user: Annotated[str | None, Header(alias="X-Test-User")] = None,
    x_test_admin: Annotated[str | None, Header(alias="X-Test-Admin")] = None,
) -> User:
    if settings.is_test:
        subject = _test_subject(x_test_user)
        user = session.exec(select(User).where(User.external_subject == subject)).first()
        if user is None:
            user = User(
                external_subject=subject,
                display_name=subject.replace("-", " ").title(),
                email=f"{subject}@example.test",
                is_admin=_is_admin_subject(subject, x_test_admin),
            )
            session.add(user)
            session.commit()
            session.refresh(user)
        elif _is_admin_subject(subject, x_test_admin) and not user.is_admin:
            user.is_admin = True
            session.add(user)
            session.commit()
            session.refresh(user)
        return user

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
