"""Доступ к медкарте по ссылке: выдача, разделы, срок, отзыв, аудит."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import AuditLog
from tests.helpers import API_V1, register_owner


def _add_record(client: TestClient, pet_id: int, **overrides) -> dict:
    payload = {
        "kind": "visit",
        "title": "Приём",
        "occurred_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        "clinic_name": "Клиника «Айболит»",
        "description": "Температура 39.2",
        "diagnosis": "ОРВИ",
    }
    payload.update(overrides)
    response = client.post(f"{API_V1}/pets/{pet_id}/records", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _grant(client: TestClient, pet_id: int, **overrides) -> dict:
    payload = {"label": "Клиника «Айболит»", "ttl_days": 7}
    payload.update(overrides)
    response = client.post(f"{API_V1}/pets/{pet_id}/access-grants", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_grant_token_is_returned_once_and_hashed(client: TestClient, pet: dict, db: Session) -> None:
    created = _grant(client, pet["id"])

    assert created["token"]
    assert created["url"].endswith(created["token"])

    listed = client.get(f"{API_V1}/pets/{pet['id']}/access-grants").json()
    assert len(listed) == 1
    assert "token" not in listed[0]

    stored_hash = db.execute(text("select token_hash from access_grants")).scalar_one()
    assert stored_hash != created["token"]
    assert len(stored_hash) == 64


def test_public_access_returns_profile_and_records(client: TestClient, pet: dict) -> None:
    _add_record(client, pet["id"])
    _add_record(
        client,
        pet["id"],
        kind="vaccination",
        title="Вакцинация от бешенства",
        diagnosis=None,
        description="Введена вакцина",
    )
    grant = _grant(client, pet["id"])

    # Ссылкой пользуется клиника — без токена авторизации.
    client.headers.pop("Authorization")
    response = client.get(f"{API_V1}/medical/access/{grant['token']}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["grant"]["label"] == "Клиника «Айболит»"
    assert body["pet"]["name"] == pet["name"]
    assert body["pet"]["age_years"] is not None
    assert len(body["records"]) == 2
    assert [row["title"] for row in body["vaccinations"]] == ["Вакцинация от бешенства"]
    # Заметки владельца не раскрываются никогда.
    assert "owner_notes" not in response.text
    assert "Аллергии" not in response.text


def test_scopes_limit_what_is_shared(client: TestClient, pet: dict) -> None:
    _add_record(client, pet["id"], kind="vaccination", title="Прививка")
    grant = _grant(client, pet["id"], scopes=["records"])

    client.headers.pop("Authorization")
    body = client.get(f"{API_V1}/medical/access/{grant['token']}").json()

    assert body["pet"] is None
    assert body["vaccinations"] is None
    assert body["records"] is not None


def test_expired_grant_is_rejected(client: TestClient, pet: dict, db: Session) -> None:
    grant = _grant(client, pet["id"])
    db.execute(
        text("update access_grants set expires_at = :expires where id = :id"),
        {"expires": datetime.now(UTC) - timedelta(minutes=1), "id": grant["id"]},
    )
    db.commit()

    client.headers.pop("Authorization")
    response = client.get(f"{API_V1}/medical/access/{grant['token']}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "access_not_found"


def test_revoked_grant_is_rejected(client: TestClient, pet: dict) -> None:
    grant = _grant(client, pet["id"])

    revoked = client.post(f"{API_V1}/access-grants/{grant['id']}/revoke")
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None

    client.headers.pop("Authorization")
    assert client.get(f"{API_V1}/medical/access/{grant['token']}").status_code == 404


def test_unknown_token_is_rejected(client: TestClient) -> None:
    response = client.get(f"{API_V1}/medical/access/no-such-token")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "access_not_found"


def test_access_read_is_audited_and_marks_last_used(client: TestClient, pet: dict, db: Session) -> None:
    grant = _grant(client, pet["id"])

    client.headers.pop("Authorization")
    assert client.get(f"{API_V1}/medical/access/{grant['token']}").status_code == 200

    db.expire_all()
    last_used = db.execute(text("select last_used_at from access_grants where id = :id"), {"id": grant["id"]}).scalar_one()
    assert last_used is not None

    actions = [row.action for row in db.query(AuditLog).all()]
    assert "access.granted" in actions
    assert "medical_access.read" in actions


def test_stranger_cannot_manage_grants(client: TestClient, client_factory, pet: dict) -> None:
    grant = _grant(client, pet["id"])
    other = client_factory()
    register_owner(other, "stranger@example.com")

    assert other.get(f"{API_V1}/pets/{pet['id']}/access-grants").status_code == 404
    assert other.post(
        f"{API_V1}/pets/{pet['id']}/access-grants", json={"label": "Чужая клиника", "ttl_days": 7}
    ).status_code == 404
    assert other.post(f"{API_V1}/access-grants/{grant['id']}/revoke").status_code == 404


def test_grant_requires_authentication(client: TestClient, pet: dict) -> None:
    client.headers.pop("Authorization")

    assert client.get(f"{API_V1}/pets/{pet['id']}/access-grants").status_code == 401


def test_ttl_is_validated(client: TestClient, pet: dict) -> None:
    assert client.post(
        f"{API_V1}/pets/{pet['id']}/access-grants", json={"label": "Слишком долго", "ttl_days": 400}
    ).status_code == 422
    assert client.post(
        f"{API_V1}/pets/{pet['id']}/access-grants", json={"label": "Ноль", "ttl_days": 0}
    ).status_code == 422
