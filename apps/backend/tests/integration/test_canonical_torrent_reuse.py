from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.models import Torrent, Video


def test_two_users_share_one_canonical_torrent(
    client: TestClient,
    session: Session,
    act_as,
    standard_user,
    second_standard_user,
) -> None:
    info_hash = "abcdefabcdefabcdefabcdefabcdefabcdefabcd"
    act_as(standard_user)
    assert client.post("/videos", json={"infoHash": info_hash, "title": "User One"}).status_code == 202
    act_as(second_standard_user)
    assert client.post("/videos", json={"infoHash": info_hash, "title": "User Two"}).status_code == 202

    assert len(session.exec(select(Torrent).where(Torrent.info_hash == info_hash)).all()) == 1
    assert len(session.exec(select(Video)).all()) == 2
