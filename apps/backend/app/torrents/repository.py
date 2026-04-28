from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.models import Torrent


def get_or_create_torrent(session: Session, info_hash: str) -> tuple[Torrent, bool]:
    torrent = session.exec(select(Torrent).where(Torrent.info_hash == info_hash)).first()
    if torrent:
        return torrent, False
    torrent = Torrent(info_hash=info_hash)
    session.add(torrent)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        torrent = session.exec(select(Torrent).where(Torrent.info_hash == info_hash)).one()
        return torrent, False
    session.refresh(torrent)
    return torrent, True
