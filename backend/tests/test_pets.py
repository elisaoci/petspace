from fastapi.testclient import TestClient

from tests.helpers import API_V1


def test_create_pet_returns_id_and_secret_token(client: TestClient, owner: dict) -> None:
    response = client.post(f"{API_V1}/pets", json={"name": "Бублик", "species": "cat", "weight_kg": 4.5})

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] > 0
    assert body["name"] == "Бублик"
    assert len(body["medical_secret_token"]) >= 20


def test_list_pets_returns_created_pets(client: TestClient, pet: dict) -> None:
    response = client.get(f"{API_V1}/pets")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [pet["id"]]


def test_update_pet_changes_only_passed_fields(client: TestClient, pet: dict) -> None:
    response = client.patch(f"{API_V1}/pets/{pet['id']}", json={"weight_kg": 33.5})

    assert response.status_code == 200
    body = response.json()
    assert body["weight_kg"] == 33.5
    assert body["breed"] == pet["breed"]


def test_delete_pet_removes_it(client: TestClient, pet: dict) -> None:
    assert client.delete(f"{API_V1}/pets/{pet['id']}").status_code == 204
    assert client.get(f"{API_V1}/pets/{pet['id']}").status_code == 404


def test_unknown_pet_returns_404(client: TestClient, owner: dict) -> None:
    assert client.get(f"{API_V1}/pets/999").status_code == 404
    assert client.patch(f"{API_V1}/pets/999", json={"name": "Нет"}).status_code == 404
    assert client.delete(f"{API_V1}/pets/999").status_code == 404


def test_renew_medical_token_changes_it(client: TestClient, pet: dict) -> None:
    response = client.post(f"{API_V1}/pets/{pet['id']}/medical-token")

    assert response.status_code == 200
    assert response.json()["medical_secret_token"] != pet["medical_secret_token"]


def test_photo_upload_saves_supported_format(client: TestClient, pet: dict, tmp_path) -> None:
    response = client.post(
        f"{API_V1}/pets/{pet['id']}/photo",
        files={"file": ("avatar.png", b"\x89PNG\r\n\x1a\n faked", "image/png")},
    )

    assert response.status_code == 200, response.text
    photo_url = response.json()["photo_url"]
    assert photo_url.startswith("/uploads/")
    saved = list((tmp_path / "uploads").glob("*.png"))
    assert len(saved) == 1


def test_photo_upload_rejects_unsupported_format(client: TestClient, pet: dict) -> None:
    response = client.post(
        f"{API_V1}/pets/{pet['id']}/photo",
        files={"file": ("payload.exe", b"MZ", "application/octet-stream")},
    )

    assert response.status_code == 400
