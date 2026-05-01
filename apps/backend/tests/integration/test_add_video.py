from fastapi.testclient import TestClient


def test_add_video_creates_visible_processed_video(client: TestClient, act_as, standard_user) -> None:
    act_as(standard_user)
    response = client.post(
        "/videos",
        json={
            "infoHash": "0123456789abcdef0123456789abcdef01234567",
            "title": "Fixture",
            "description": "Personal note",
            "rating": 5,
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["title"] == "Fixture"
    assert body["description"] == "Personal note"
    assert body["metadataStatus"] == "succeeded"
    assert body["files"][0]["path"] == "Fixture Movie/video.mp4"
