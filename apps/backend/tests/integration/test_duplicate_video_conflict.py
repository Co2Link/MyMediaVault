from fastapi.testclient import TestClient


def test_same_user_duplicate_video_conflicts(client: TestClient) -> None:
    info_hash = "abcdefabcdefabcdefabcdefabcdefabcdefabcd"
    assert client.post("/videos", json={"infoHash": info_hash}).status_code == 202
    assert client.post("/videos", json={"infoHash": info_hash}).status_code == 409
