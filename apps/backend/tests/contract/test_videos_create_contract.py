from fastapi.testclient import TestClient

VALID_HASH = "0123456789abcdef0123456789abcdef01234567"


def test_post_videos_accepts_valid_hash(client: TestClient) -> None:
    response = client.post("/videos", json={"infoHash": VALID_HASH, "title": "Fixture"})
    assert response.status_code == 202
    body = response.json()
    assert body["infoHash"] == VALID_HASH
    assert body["metadataStatus"] == "succeeded"


def test_post_videos_rejects_invalid_hash(client: TestClient) -> None:
    response = client.post("/videos", json={"infoHash": "bad"})
    assert response.status_code == 400


def test_post_videos_conflicts_for_duplicate_personal_entry(client: TestClient) -> None:
    assert client.post("/videos", json={"infoHash": VALID_HASH}).status_code == 202
    response = client.post("/videos", json={"infoHash": VALID_HASH})
    assert response.status_code == 409
