from fastapi.testclient import TestClient

VALID_HASH = "0123456789abcdef0123456789abcdef01234567"


def test_get_videos_returns_collection(client: TestClient, act_as, standard_user) -> None:
    act_as(standard_user)
    client.post("/videos", json={"infoHash": VALID_HASH, "title": "Find Me", "rating": 4})
    response = client.get("/videos", params={"q": "Find"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Find Me"


def test_get_video_returns_detail(client: TestClient, act_as, standard_user) -> None:
    act_as(standard_user)
    created = client.post("/videos", json={"infoHash": VALID_HASH}).json()
    response = client.get(f"/videos/{created['id']}")
    assert response.status_code == 200
    assert response.json()["metadataStatus"] == "pending"


def test_patch_video_updates_user_specific_details(client: TestClient, act_as, standard_user) -> None:
    act_as(standard_user)
    created = client.post("/videos", json={"infoHash": VALID_HASH, "title": "Original"}).json()

    response = client.patch(
        f"/videos/{created['id']}",
        json={"title": "Updated", "description": "Personal note", "rating": 5},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Updated"
    assert body["description"] == "Personal note"
    assert body["rating"] == 5
