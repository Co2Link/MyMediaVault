from fastapi.testclient import TestClient

ADMIN_HEADERS = {"X-Test-User": "admin", "X-Test-Admin": "true"}


def test_admin_tag_create_rename_delete(client: TestClient) -> None:
    created = client.post("/admin/tags", json={"name": "Sci Fi"}, headers=ADMIN_HEADERS)
    tag_id = created.json()["id"]
    assert created.status_code == 201

    duplicate = client.post("/admin/tags", json={"name": "Sci Fi"}, headers=ADMIN_HEADERS)
    assert duplicate.status_code == 409

    renamed = client.patch(f"/admin/tags/{tag_id}", json={"name": "Science Fiction"}, headers=ADMIN_HEADERS)
    assert renamed.json()["name"] == "Science Fiction"

    deleted = client.delete(f"/admin/tags/{tag_id}", headers=ADMIN_HEADERS)
    assert deleted.status_code == 204
