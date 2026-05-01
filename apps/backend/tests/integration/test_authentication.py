from fastapi.testclient import TestClient


def test_protected_route_requires_token(client: TestClient) -> None:
    response = client.get("/videos")

    assert response.status_code == 403
    assert response.json()["message"] == "Authentication is required"


def test_protected_route_rejects_invalid_token(client: TestClient) -> None:
    response = client.get("/videos", headers={"Authorization": "Bearer invalid"})

    assert response.status_code == 403
    assert response.json()["message"] == "Authentication token is invalid"
