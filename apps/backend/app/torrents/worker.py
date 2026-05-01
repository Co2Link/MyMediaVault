from collections.abc import Callable
from threading import Event, Thread
from uuid import uuid4

from sqlmodel import Session

from app.core.config import Settings
from app.core.db import engine
from app.storage.blob_store import build_blob_store
from app.torrents.provider import TorrentMetadataProvider
from app.torrents.service import (
    claim_torrent_processing_job,
    heartbeat_torrent_processing_job,
    process_torrent_metadata,
)


SessionFactory = Callable[[], Session]


def default_session_factory() -> Session:
    return Session(engine)


def run_torrent_processing_cycle(
    session_factory: SessionFactory,
    provider: TorrentMetadataProvider,
    settings: Settings,
    worker_id: str | None = None,
) -> int:
    resolved_worker_id = worker_id or f"worker-{uuid4()}"
    with session_factory() as session:
        job = claim_torrent_processing_job(session, resolved_worker_id, settings.torrent_job_lease_seconds)
        if job is None:
            return 0
        heartbeat_torrent_processing_job(session, job.id, settings.torrent_job_lease_seconds)
        process_torrent_metadata(session, job.id, provider, build_blob_store(settings))
        return 1


class TorrentProcessingWorker:
    def __init__(
        self,
        settings: Settings,
        provider: TorrentMetadataProvider,
        session_factory: SessionFactory = default_session_factory,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.session_factory = session_factory
        self.stop_event = Event()
        self.thread = Thread(target=self._run, name="torrent-processing-worker", daemon=True)
        self.worker_id = f"worker-{uuid4()}"

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=max(self.settings.torrent_worker_poll_interval_seconds * 2, 1.0))

    def _run(self) -> None:
        while not self.stop_event.is_set():
            processed = run_torrent_processing_cycle(
                session_factory=self.session_factory,
                provider=self.provider,
                settings=self.settings,
                worker_id=self.worker_id,
            )
            if processed == 0:
                self.stop_event.wait(self.settings.torrent_worker_poll_interval_seconds)
