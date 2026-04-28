from sqlmodel import Session, col, delete

from app.core.models import Torrent, TorrentFile, TorrentJobStatus, TorrentMetadataStatus, TorrentProcessingJob, utcnow
from app.storage.blob_store import BlobStore
from app.torrents.provider import TorrentMetadataProvider


def process_torrent_metadata(
    session: Session,
    torrent: Torrent,
    provider: TorrentMetadataProvider,
    blob_store: BlobStore,
) -> Torrent:
    job = TorrentProcessingJob(torrent_id=torrent.id, status=TorrentJobStatus.RUNNING, started_at=utcnow())
    session.add(job)
    torrent.metadata_status = TorrentMetadataStatus.PROCESSING
    torrent.metadata_attempts += 1
    torrent.metadata_last_attempt_at = utcnow()
    session.add(torrent)
    session.commit()

    try:
        metadata = provider.fetch(torrent.info_hash)
        blob_key = f"torrents/{torrent.info_hash}.torrent"
        blob_store.put_bytes(blob_key, metadata.raw)
        session.exec(delete(TorrentFile).where(col(TorrentFile.torrent_id) == torrent.id))
        torrent.name = metadata.name
        torrent.size_bytes = metadata.size_bytes
        torrent.raw_blob_key = blob_key
        torrent.metadata_status = TorrentMetadataStatus.SUCCEEDED
        torrent.metadata_error = None
        torrent.updated_at = utcnow()
        for position, file in enumerate(metadata.files):
            session.add(
                TorrentFile(torrent_id=torrent.id, path=file.path, size_bytes=file.size_bytes, position=position)
            )
        job.status = TorrentJobStatus.SUCCEEDED
    except Exception as exc:  # pragma: no cover - provider-specific
        torrent.metadata_status = TorrentMetadataStatus.FAILED
        torrent.metadata_error = str(exc)
        job.status = TorrentJobStatus.FAILED
        job.error = str(exc)
    finally:
        job.finished_at = utcnow()
        session.add(torrent)
        session.add(job)
        session.commit()
        session.refresh(torrent)
    return torrent
