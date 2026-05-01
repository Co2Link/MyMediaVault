from fastapi.testclient import TestClient


def test_user_cannot_read_other_users_video(client: TestClient, act_as, standard_user, second_standard_user) -> None:
    act_as(standard_user)
    created = client.post("/videos", json={"infoHash": "0123456789abcdef0123456789abcdef01234567"}).json()

    act_as(second_standard_user)
    response = client.get(f"/videos/{created['id']}")
    assert response.status_code == 404


def test_user_cannot_update_other_users_video(client: TestClient, act_as, standard_user, second_standard_user) -> None:
    act_as(standard_user)
    created = client.post(
        "/videos",
        json={"infoHash": "0123456789abcdef0123456789abcdef01234567", "title": "Owned"},
    ).json()

    act_as(second_standard_user)
    response = client.patch(f"/videos/{created['id']}", json={"title": "Hijacked"})

    assert response.status_code == 404
