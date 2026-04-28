from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.models import Torrent, Video


def test_two_users_share_one_canonical_torrent(client: TestClient, session: Session) -> None:
    info_hash = "abcdefabcdefabcdefabcdefabcdefabcdefabcd"
    assert (
        client.post(
            "/videos", json={"infoHash": info_hash, "title": "User One"}, headers={"X-Test-User": "one"}
        ).status_code
        == 202
    )
    assert (
        client.post(
            "/videos", json={"infoHash": info_hash, "title": "User Two"}, headers={"X-Test-User": "two"}
        ).status_code
        == 202
    )

    assert len(session.exec(select(Torrent).where(Torrent.info_hash == info_hash)).all()) == 1
    assert len(session.exec(select(Video)).all()) == 2
