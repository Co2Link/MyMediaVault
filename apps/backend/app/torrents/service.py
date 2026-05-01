from datetime import timedelta
from uuid import UUID

from sqlalchemy import and_, or_
from sqlmodel import Session, col, delete, select

from app.core.models import Torrent, TorrentFile, TorrentJobStatus, TorrentMetadataStatus, TorrentProcessingJob, utcnow
from app.storage.blob_store import BlobStore
from app.torrents.provider import TorrentMetadataProvider


def enqueue_torrent_metadata(session: Session, torrent: Torrent) -> TorrentProcessingJob | None:
    if torrent.metadata_status == TorrentMetadataStatus.SUCCEEDED and torrent.raw_blob_key:
        return None

    active_job = session.exec(
        select(TorrentProcessingJob).where(
            TorrentProcessingJob.torrent_id == torrent.id,
            col(TorrentProcessingJob.status).in_((TorrentJobStatus.QUEUED, TorrentJobStatus.RUNNING)),
        )
    ).first()
    if active_job:
        return active_job

    torrent.metadata_status = TorrentMetadataStatus.PENDING
    torrent.metadata_error = None
    session.add(torrent)
    job = TorrentProcessingJob(
        torrent_id=torrent.id, status=TorrentJobStatus.QUEUED, attempt=torrent.metadata_attempts + 1
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def claim_torrent_processing_job(session: Session, worker_id: str, lease_seconds: int) -> TorrentProcessingJob | None:
    now = utcnow()
    job_status = col(TorrentProcessingJob.status)
    lease_expires_at = col(TorrentProcessingJob.lease_expires_at)
    job = session.exec(
        select(TorrentProcessingJob)
        .where(
            or_(
                job_status == TorrentJobStatus.QUEUED,
                and_(
                    job_status == TorrentJobStatus.RUNNING,
                    lease_expires_at.is_not(None),
                    lease_expires_at < now,
                ),
            )
        )
        .order_by(col(TorrentProcessingJob.created_at), col(TorrentProcessingJob.id))
    ).first()
    if job is None:
        return None

    job.status = TorrentJobStatus.RUNNING
    job.worker_id = worker_id
    job.started_at = job.started_at or now
    job.finished_at = None
    job.error = None
    job.last_heartbeat_at = now
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    session.add(job)
    torrent = session.get(Torrent, job.torrent_id)
    if torrent is not None:
        torrent.metadata_status = TorrentMetadataStatus.PROCESSING
        torrent.metadata_attempts = max(torrent.metadata_attempts, job.attempt)
        torrent.metadata_last_attempt_at = now
        session.add(torrent)
    session.commit()
    session.refresh(job)
    return job


def heartbeat_torrent_processing_job(session: Session, job_id: UUID, lease_seconds: int) -> None:
    job = session.get(TorrentProcessingJob, job_id)
    if job is None or job.status != TorrentJobStatus.RUNNING:
        return
    now = utcnow()
    job.last_heartbeat_at = now
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    session.add(job)
    session.commit()


def process_torrent_metadata(
    session: Session,
    job_id: UUID,
    provider: TorrentMetadataProvider,
    blob_store: BlobStore,
) -> Torrent:
    job = session.get(TorrentProcessingJob, job_id)
    if job is None:
        raise ValueError("Torrent processing job was not found")
    torrent = session.get(Torrent, job.torrent_id)
    if torrent is None:
        raise ValueError("Torrent was not found")

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
        finished_at = utcnow()
        job.finished_at = finished_at
        job.lease_expires_at = None
        job.last_heartbeat_at = finished_at
        session.add(torrent)
        session.add(job)
        session.commit()
        session.refresh(torrent)
    return torrent
