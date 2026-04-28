from fastapi.testclient import TestClient


def test_search_collection_by_title_and_empty_result(client: TestClient) -> None:
    client.post(
        "/videos",
        json={"infoHash": "0123456789abcdef0123456789abcdef01234567", "title": "Ocean Film", "rating": 3},
    )
    found = client.get("/videos", params={"q": "Ocean"})
    assert found.json()["total"] == 1

    missing = client.get("/videos", params={"q": "Missing"})
    assert missing.json()["total"] == 0
