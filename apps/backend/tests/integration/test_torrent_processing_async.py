from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.models import Torrent, TorrentJobStatus, TorrentMetadataStatus, TorrentProcessingJob


def test_processing_cycle_populates_torrent_metadata(
    client: TestClient,
    session: Session,
    act_as,
    standard_user,
    run_processing_cycle,
) -> None:
    act_as(standard_user)
    response = client.post("/videos", json={"infoHash": "0123456789abcdef0123456789abcdef01234567"})

    assert response.status_code == 202
    body = response.json()
    assert body["metadataStatus"] == "pending"
    assert run_processing_cycle() == 1

    refreshed = client.get(f"/videos/{body['id']}")
    assert refreshed.status_code == 200
    detail = refreshed.json()
    assert detail["metadataStatus"] == "succeeded"
    assert detail["files"][0]["path"] == "Fixture Movie/video.mp4"

    torrent = session.exec(select(Torrent).where(Torrent.info_hash == body["infoHash"])).one()
    assert torrent.raw_blob_key == f"torrents/{body['infoHash']}.torrent"
    jobs = session.exec(select(TorrentProcessingJob).where(TorrentProcessingJob.torrent_id == torrent.id)).all()
    assert len(jobs) == 1
    assert jobs[0].status == TorrentJobStatus.SUCCEEDED


def test_duplicate_adds_share_one_active_processing_job(
    client: TestClient,
    session: Session,
    act_as,
    standard_user,
    second_standard_user,
) -> None:
    info_hash = "abcdefabcdefabcdefabcdefabcdefabcdefabcd"
    act_as(standard_user)
    assert client.post("/videos", json={"infoHash": info_hash}).status_code == 202
    act_as(second_standard_user)
    assert client.post("/videos", json={"infoHash": info_hash}).status_code == 202

    torrent = session.exec(select(Torrent).where(Torrent.info_hash == info_hash)).one()
    assert torrent.metadata_status == TorrentMetadataStatus.PENDING
    jobs = session.exec(select(TorrentProcessingJob).where(TorrentProcessingJob.torrent_id == torrent.id)).all()
    assert len(jobs) == 1
    assert jobs[0].status == TorrentJobStatus.QUEUED
