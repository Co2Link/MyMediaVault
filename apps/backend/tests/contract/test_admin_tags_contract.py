from fastapi.testclient import TestClient

from app.core.models import User


def test_admin_tag_crud_contract(client: TestClient, act_as, admin_user: User) -> None:
    act_as(admin_user)
    created = client.post("/admin/tags", json={"name": "Drama"})
    assert created.status_code == 201
    tag_id = created.json()["id"]

    listed = client.get("/admin/tags")
    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "Drama"

    updated = client.patch(f"/admin/tags/{tag_id}", json={"name": "Classic"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Classic"

    deleted = client.delete(f"/admin/tags/{tag_id}")
    assert deleted.status_code == 204


def test_admin_tags_forbid_standard_user(client: TestClient, act_as, standard_user: User) -> None:
    act_as(standard_user)
    response = client.post("/admin/tags", json={"name": "Drama"})
    assert response.status_code == 403
