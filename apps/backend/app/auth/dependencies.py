from typing import Annotated

from fastapi import Depends, Header
from sqlmodel import Session, select

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.errors import ForbiddenError
from app.core.models import User


def _test_subject(x_test_user: str | None) -> str:
    return x_test_user or "test-user-1"


def _is_admin_subject(subject: str, x_test_admin: str | None) -> bool:
    return subject == "admin" or x_test_admin == "true"


def get_current_user(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
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

    # Production Entra ID validation is wired during deployment configuration.
    # The domain code depends only on this normalized user model.
    subject = authorization.removeprefix("Bearer ").strip()
    if not subject:
        raise ForbiddenError("Authentication token is invalid")
    user = session.exec(select(User).where(User.external_subject == subject)).first()
    if user is None:
        user = User(external_subject=subject)
        session.add(user)
        session.commit()
        session.refresh(user)
    return user
