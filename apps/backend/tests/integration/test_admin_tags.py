from fastapi.testclient import TestClient

from app.core.models import User


def test_admin_tag_create_rename_delete(client: TestClient, act_as, admin_user: User) -> None:
    act_as(admin_user)
    created = client.post("/admin/tags", json={"name": "Sci Fi"})
    tag_id = created.json()["id"]
    assert created.status_code == 201

    duplicate = client.post("/admin/tags", json={"name": "Sci Fi"})
    assert duplicate.status_code == 409

    renamed = client.patch(f"/admin/tags/{tag_id}", json={"name": "Science Fiction"})
    assert renamed.json()["name"] == "Science Fiction"

    deleted = client.delete(f"/admin/tags/{tag_id}")
    assert deleted.status_code == 204
