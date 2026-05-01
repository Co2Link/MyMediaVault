from collections.abc import Generator
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.routers.videos import get_torrent_provider
from app.auth.dependencies import get_current_user
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.models import User
from app.storage.blob_store import build_blob_store
from app.main import create_app
from app.torrents.provider import FakeTorrentMetadataProvider, TorrentFileMetadata, TorrentMetadata
from app.torrents.service import claim_torrent_processing_job, process_torrent_metadata


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def provider() -> FakeTorrentMetadataProvider:
    fixture_hash = "0123456789abcdef0123456789abcdef01234567"
    duplicate_hash = "abcdefabcdefabcdefabcdefabcdefabcdefabcd"
    metadata = TorrentMetadata(
        name="Fixture Movie",
        size_bytes=300,
        files=(
            TorrentFileMetadata(path="Fixture Movie/video.mp4", size_bytes=250),
            TorrentFileMetadata(path="Fixture Movie/readme.txt", size_bytes=50),
        ),
        raw=b"d4:infod6:lengthi250e4:name9:video.mp4ee",
    )
    return FakeTorrentMetadataProvider({fixture_hash: metadata, duplicate_hash: metadata})


@pytest.fixture()
def client(
    session: Session, provider: FakeTorrentMetadataProvider, settings: Settings
) -> Generator[TestClient, None, None]:
    app = create_app(settings)

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_torrent_provider] = lambda: provider
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        blob_storage_root=tmp_path,
        torrent_worker_enabled=False,
        entra_tenant_id="tenant-id",
        entra_client_id="backend-client-id",
        entra_openapi_client_id="openapi-client-id",
        entra_api_scope="access_as_user",
    )


@pytest.fixture()
def run_processing_cycle(session: Session, provider: FakeTorrentMetadataProvider, settings: Settings):
    def _run() -> int:
        job = claim_torrent_processing_job(session, "test-worker", settings.torrent_job_lease_seconds)
        if job is None:
            return 0
        process_torrent_metadata(session, job.id, provider, build_blob_store(settings))
        return 1

    return _run


def _persist_user(
    session: Session,
    *,
    subject: str,
    display_name: str,
    email: str,
    is_admin: bool = False,
) -> User:
    user = User(external_subject=subject, display_name=display_name, email=email, is_admin=is_admin)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture()
def standard_user(session: Session) -> User:
    return _persist_user(
        session,
        subject="test-user-1",
        display_name="Test User 1",
        email="test-user-1@example.test",
    )


@pytest.fixture()
def second_standard_user(session: Session) -> User:
    return _persist_user(
        session,
        subject="test-user-2",
        display_name="Test User 2",
        email="test-user-2@example.test",
    )


@pytest.fixture()
def admin_user(session: Session) -> User:
    return _persist_user(
        session,
        subject="admin",
        display_name="Admin User",
        email="admin@example.test",
        is_admin=True,
    )


@pytest.fixture()
def act_as(client: TestClient):
    def _act_as(user: User | None) -> None:
        app = cast(FastAPI, client.app)
        if user is None:
            app.dependency_overrides.pop(get_current_user, None)
            return
        app.dependency_overrides[get_current_user] = lambda: user

    return _act_as
