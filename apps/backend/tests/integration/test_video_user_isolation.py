from fastapi.testclient import TestClient


def test_user_cannot_read_other_users_video(client: TestClient) -> None:
    created = client.post(
        "/videos",
        json={"infoHash": "0123456789abcdef0123456789abcdef01234567"},
        headers={"X-Test-User": "test-user-1"},
    ).json()

    response = client.get(f"/videos/{created['id']}", headers={"X-Test-User": "test-user-2"})
    assert response.status_code == 404
