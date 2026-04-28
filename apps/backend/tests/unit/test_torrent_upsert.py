from sqlmodel import Session

from app.torrents.repository import get_or_create_torrent


def test_get_or_create_torrent_reuses_existing_record(session: Session) -> None:
    torrent, created = get_or_create_torrent(session, "0123456789abcdef0123456789abcdef01234567")
    assert created is True

    second, second_created = get_or_create_torrent(session, torrent.info_hash)
    assert second_created is False
    assert second.id == torrent.id
