from app.core.errors import ForbiddenError
from app.core.models import User


def require_admin(user: User) -> User:
    if not user.is_admin:
        raise ForbiddenError("Administrator privileges are required")
    return user
