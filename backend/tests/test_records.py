"""Smart-ID: медзаписи, история изменений и шифрование текстов."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.helpers import API_V1, register_owner


def _record_payload(**overrides) -> dict:
    payload = {
        "kind": "visit",
        "title": "Приём в клинике",
        "occurred_at": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
        "clinic_name": "Клиника «Айболит»",
        "description": "Кот отказывается от еды второй день",
        "diagnosis": "Гастрит, назначена диета",
    }
    payload.update(overrides)
    return payload


def test_create_and_list_records(client: TestClient, pet: dict) -> None:
    created = client.post(f"{API_V1}/pets/{pet['id']}/records", json=_record_payload())

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["author_type"] == "owner"
    assert body["source"] == "manual"
    assert body["title"] == "Приём в клинике"

    listed = client.get(f"{API_V1}/pets/{pet['id']}/records")
    assert listed.status_code == 200
    assert listed.headers["X-Total-Count"] == "1"
    assert listed.json()[0]["id"] == body["id"]


def test_records_are_ordered_newest_first(client: TestClient, pet: dict) -> None:
    old = client.post(
        f"{API_V1}/pets/{pet['id']}/records",
        json=_record_payload(title="Старый приём", occurred_at=(datetime.now(UTC) - timedelta(days=30)).isoformat()),
    ).json()
    fresh = client.post(
        f"{API_V1}/pets/{pet['id']}/records",
        json=_record_payload(title="Новый приём", occurred_at=datetime.now(UTC).isoformat()),
    ).json()

    titles = [row["title"] for row in client.get(f"{API_V1}/pets/{pet['id']}/records").json()]

    assert titles == [fresh["title"], old["title"]]


def test_record_texts_are_encrypted_at_rest(client: TestClient, pet: dict, db: Session) -> None:
    created = client.post(f"{API_V1}/pets/{pet['id']}/records", json=_record_payload()).json()

    raw = db.execute(
        text("select description, diagnosis from medical_records where id = :id"), {"id": created["id"]}
    ).one()

    assert raw.description.startswith("enc:v1:")
    assert raw.diagnosis.startswith("enc:v1:")
    assert "Гастрит" not in raw.diagnosis

    # Через API значения расшифрованы.
    fetched = client.get(f"{API_V1}/records/{created['id']}").json()
    assert fetched["diagnosis"] == "Гастрит, назначена диета"


def test_update_keeps_history(client: TestClient, pet: dict) -> None:
    created = client.post(f"{API_V1}/pets/{pet['id']}/records", json=_record_payload()).json()

    updated = client.patch(
        f"{API_V1}/records/{created['id']}",
        json={"title": "Повторный приём", "diagnosis": "Улучшение"},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Повторный приём"
    assert updated.json()["clinic_name"] == "Клиника «Айболит»"

    revisions = client.get(f"{API_V1}/records/{created['id']}/revisions").json()
    assert [row["action"] for row in revisions] == ["updated", "created"]

    # Снимок содержит прежние значения.
    before = client.get(f"{API_V1}/records/{created['id']}/revisions/{revisions[0]['id']}").json()["before"]
    assert before["title"] == "Приём в клинике"
    assert before["diagnosis"] == "Гастрит, назначена диета"


def test_revision_snapshot_is_encrypted_at_rest(client: TestClient, pet: dict, db: Session) -> None:
    created = client.post(f"{API_V1}/pets/{pet['id']}/records", json=_record_payload()).json()
    client.patch(f"{API_V1}/records/{created['id']}", json={"title": "Новый заголовок"})

    raw = db.execute(
        text("select snapshot from record_revisions where record_id = :id and action = 'updated'"),
        {"id": created["id"]},
    ).scalar_one()

    assert raw.startswith("enc:v1:")
    assert "Приём в клинике" not in raw


def test_delete_record(client: TestClient, pet: dict) -> None:
    created = client.post(f"{API_V1}/pets/{pet['id']}/records", json=_record_payload()).json()

    assert client.delete(f"{API_V1}/records/{created['id']}").status_code == 204
    assert client.get(f"{API_V1}/records/{created['id']}").status_code == 404
    assert client.get(f"{API_V1}/pets/{pet['id']}/records").json() == []


def test_record_requires_authentication(client: TestClient, pet: dict) -> None:
    client.headers.pop("Authorization")

    assert client.get(f"{API_V1}/pets/{pet['id']}/records").status_code == 401


def test_stranger_cannot_touch_records(client: TestClient, client_factory, pet: dict) -> None:
    created = client.post(f"{API_V1}/pets/{pet['id']}/records", json=_record_payload()).json()

    other = client_factory()
    register_owner(other, "stranger@example.com")

    assert other.get(f"{API_V1}/pets/{pet['id']}/records").status_code == 404
    assert other.get(f"{API_V1}/records/{created['id']}").status_code == 404
    assert other.patch(f"{API_V1}/records/{created['id']}", json={"title": "Чужое"}).status_code == 404
    assert other.delete(f"{API_V1}/records/{created['id']}").status_code == 404

    # Владелец видит запись неизменной.
    assert client.get(f"{API_V1}/records/{created['id']}").json()["title"] == created["title"]


@pytest.mark.parametrize("kind", ["visit", "vaccination", "lab", "prescription", "other"])
def test_supported_kinds(client: TestClient, pet: dict, kind: str) -> None:
    response = client.post(f"{API_V1}/pets/{pet['id']}/records", json=_record_payload(kind=kind))

    assert response.status_code == 201
    assert response.json()["kind"] == kind


def test_unknown_kind_is_rejected(client: TestClient, pet: dict) -> None:
    response = client.post(f"{API_V1}/pets/{pet['id']}/records", json=_record_payload(kind="surgery"))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
