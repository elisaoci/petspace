from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.helpers import API_V1


def test_medical_records_are_encrypted_and_shared_read_only(
    client: TestClient, pet: dict, db: Session
) -> None:
    record_response = client.post(
        f"{API_V1}/pets/{pet['id']}/records",
        json={
            "kind": "visit",
            "title": "Осмотр",
            "occurred_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            "clinic_name": "Клиника",
            "description": "Чувствительные заметки",
            "diagnosis": "Назначение",
        },
    )
    assert record_response.status_code == 201, record_response.text
    record = record_response.json()

    encrypted = db.execute(
        text("select description, diagnosis from medical_records where id = :id"),
        {"id": record["id"]},
    ).one()
    assert encrypted.description.startswith("enc:v1:")
    assert encrypted.diagnosis.startswith("enc:v1:")

    grant_response = client.post(
        f"{API_V1}/pets/{pet['id']}/access-grants",
        json={"label": "Клиника", "ttl_days": 7, "scopes": ["profile", "records"]},
    )
    assert grant_response.status_code == 201, grant_response.text
    grant = grant_response.json()

    client.headers.pop("Authorization")
    shared = client.get(f"{API_V1}/medical/access/{grant['token']}")
    assert shared.status_code == 200, shared.text
    body = shared.json()
    assert body["pet"]["name"] == pet["name"]
    assert body["records"][0]["diagnosis"] == "Назначение"
    assert body["vaccinations"] is None
    assert "owner_notes" not in shared.text


def test_revoked_smart_id_access_is_not_usable(client: TestClient, pet: dict) -> None:
    grant_response = client.post(
        f"{API_V1}/pets/{pet['id']}/access-grants",
        json={"label": "Клиника", "ttl_days": 7},
    )
    assert grant_response.status_code == 201, grant_response.text
    grant = grant_response.json()

    revoked = client.post(f"{API_V1}/access-grants/{grant['id']}/revoke")
    assert revoked.status_code == 200
    client.headers.pop("Authorization")

    response = client.get(f"{API_V1}/medical/access/{grant['token']}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "access_not_found"
