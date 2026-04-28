import pytest

from app.core.errors import AppError
from app.videos.validation import normalize_info_hash, validate_rating


def test_normalize_info_hash_accepts_hex() -> None:
    assert normalize_info_hash("ABCDEFABCDEFABCDEFABCDEFABCDEFABCDEFABCD") == "abcdefabcdefabcdefabcdefabcdefabcdefabcd"


def test_normalize_info_hash_rejects_invalid_value() -> None:
    with pytest.raises(AppError):
        normalize_info_hash("bad")


def test_validate_rating_range() -> None:
    assert validate_rating(5) == 5
    with pytest.raises(AppError):
        validate_rating(6)
