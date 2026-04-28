import re

from app.core.errors import AppError

INFO_HASH_RE = re.compile(r"^[A-Fa-f0-9]{40}$|^[A-Fa-f0-9]{64}$|^[A-Za-z2-7]{32}$")


def normalize_info_hash(value: str) -> str:
    normalized = value.strip().lower()
    if not INFO_HASH_RE.fullmatch(normalized):
        raise AppError("Info hash must be a 40-character hex, 64-character hex, or 32-character base32 value")
    return normalized


def validate_rating(value: int | None) -> int | None:
    if value is None:
        return None
    if value < 1 or value > 5:
        raise AppError("Rating must be between 1 and 5")
    return value
