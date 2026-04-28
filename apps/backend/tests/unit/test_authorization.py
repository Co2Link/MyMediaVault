import pytest

from app.auth.authorization import require_admin
from app.core.errors import ForbiddenError
from app.core.models import User


def test_require_admin_allows_admin() -> None:
    user = User(external_subject="admin", is_admin=True)
    assert require_admin(user) is user


def test_require_admin_rejects_standard_user() -> None:
    with pytest.raises(ForbiddenError):
        require_admin(User(external_subject="user", is_admin=False))
