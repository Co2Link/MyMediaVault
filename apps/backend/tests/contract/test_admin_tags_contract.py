from fastapi.testclient import TestClient

ADMIN_HEADERS = {"X-Test-User": "admin", "X-Test-Admin": "true"}


def test_admin_tag_crud_contract(client: TestClient) -> None:
    created = client.post("/admin/tags", json={"name": "Drama"}, headers=ADMIN_HEADERS)
    assert created.status_code == 201
    tag_id = created.json()["id"]

    listed = client.get("/admin/tags", headers=ADMIN_HEADERS)
    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "Drama"

    updated = client.patch(f"/admin/tags/{tag_id}", json={"name": "Classic"}, headers=ADMIN_HEADERS)
    assert updated.status_code == 200
    assert updated.json()["name"] == "Classic"

    deleted = client.delete(f"/admin/tags/{tag_id}", headers=ADMIN_HEADERS)
    assert deleted.status_code == 204


def test_admin_tags_forbid_standard_user(client: TestClient) -> None:
    response = client.post("/admin/tags", json={"name": "Drama"})
    assert response.status_code == 403
