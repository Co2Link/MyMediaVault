from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.routers.videos import get_torrent_provider
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.main import create_app
from app.torrents.provider import FakeTorrentMetadataProvider, TorrentFileMetadata, TorrentMetadata


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
    session: Session, provider: FakeTorrentMetadataProvider, tmp_path: Path
) -> Generator[TestClient, None, None]:
    app = create_app()

    def override_session() -> Generator[Session, None, None]:
        yield session

    def override_settings() -> Settings:
        return Settings(environment="test", test_mode=True, blob_storage_root=tmp_path)

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_torrent_provider] = lambda: provider
    with TestClient(app) as test_client:
        yield test_client
