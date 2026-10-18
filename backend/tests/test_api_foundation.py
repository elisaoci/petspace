"""Единый формат ошибок, пагинация и идемпотентность записи."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import IdempotencyKey
from tests.helpers import API_V1, register_owner

# --- Формат ошибок ---------------------------------------------------------


def test_error_envelope_for_not_found(client: TestClient, owner: dict) -> None:
    body = client.get(f"{API_V1}/pets/999").json()

    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "Pet not found"
    # legacy-поле сохраняется для старых клиентов
    assert body["detail"] == "Pet not found"


def test_error_envelope_for_unauthorized(client: TestClient) -> None:
    body = client.get(f"{API_V1}/pets").json()

    assert body["error"]["code"] == "unauthorized"
    assert body["error"]["message"]


def test_error_envelope_for_validation(client: TestClient, owner: dict) -> None:
    response = client.post(f"{API_V1}/pets", json={"name": "Макс", "birth_date": "не дата"})

    body = response.json()
    assert response.status_code == 422
    assert body["error"]["code"] == "validation_error"
    assert isinstance(body["error"]["details"], list)


def test_error_envelope_keeps_domain_code(client: TestClient, owner: dict, db: Session) -> None:
    from app.models import Consent

    db.query(Consent).filter(Consent.user_id == owner["user"]["id"]).delete()
    db.commit()

    body = client.post(f"{API_V1}/pets", json={"name": "Без согласий"}).json()

    assert body["error"]["code"] == "consent_required"
    assert body["error"]["details"]["kinds"] == ["terms", "privacy"]


# --- Пагинация -------------------------------------------------------------


def test_list_pets_reports_total_and_limits(client: TestClient, owner: dict) -> None:
    for name in ("А", "Б", "В"):
        assert client.post(f"{API_V1}/pets", json={"name": name}).status_code == 201

    first_page = client.get(f"{API_V1}/pets", params={"limit": 2})

    assert first_page.headers["X-Total-Count"] == "3"
    assert first_page.headers["X-Limit"] == "2"
    assert len(first_page.json()) == 2

    second_page = client.get(f"{API_V1}/pets", params={"limit": 2, "offset": 2})
    assert len(second_page.json()) == 1
    assert {item["id"] for item in first_page.json()}.isdisjoint({item["id"] for item in second_page.json()})


def test_list_rejects_too_large_limit(client: TestClient, owner: dict) -> None:
    response = client.get(f"{API_V1}/pets", params={"limit": 500})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_events_pagination(client: TestClient, pet: dict) -> None:
    for index in range(3):
        client.post(
            f"{API_V1}/events",
            json={
                "pet_id": pet["id"],
                "title": f"Событие {index}",
                "starts_at": (datetime.now(UTC) + timedelta(days=index + 1)).isoformat(),
            },
        )

    response = client.get(f"{API_V1}/events", params={"pet_id": pet["id"], "limit": 2})

    assert response.headers["X-Total-Count"] == "3"
    assert len(response.json()) == 2


# --- Идемпотентность -------------------------------------------------------


def test_same_idempotency_key_returns_stored_response(client: TestClient, owner: dict) -> None:
    payload = {"name": "Бублик"}
    headers = {"Idempotency-Key": "create-bublik"}

    first = client.post(f"{API_V1}/pets", json=payload, headers=headers)
    second = client.post(f"{API_V1}/pets", json=payload, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.headers["Idempotent-Replay"] == "true"
    assert second.json()["id"] == first.json()["id"]
    assert len(client.get(f"{API_V1}/pets").json()) == 1


def test_same_key_with_different_body_conflicts(client: TestClient, owner: dict) -> None:
    headers = {"Idempotency-Key": "create-conflict"}
    assert client.post(f"{API_V1}/pets", json={"name": "Первый"}, headers=headers).status_code == 201

    response = client.post(f"{API_V1}/pets", json={"name": "Второй"}, headers=headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_conflict"


def test_without_key_repeated_requests_create_duplicates(client: TestClient, owner: dict) -> None:
    client.post(f"{API_V1}/pets", json={"name": "Двойник"})
    client.post(f"{API_V1}/pets", json={"name": "Двойник"})

    assert len(client.get(f"{API_V1}/pets").json()) == 2


def test_idempotency_key_is_scoped_by_user(client: TestClient, client_factory, owner: dict) -> None:
    assert client.post(
        f"{API_V1}/pets", json={"name": "Мой"}, headers={"Idempotency-Key": "shared-key"}
    ).status_code == 201

    other = client_factory()
    register_owner(other, "second@example.com")
    response = other.post(f"{API_V1}/pets", json={"name": "Свой"}, headers={"Idempotency-Key": "shared-key"})

    assert response.status_code == 201
    assert response.json()["name"] == "Свой"


def test_idempotency_key_expires(client: TestClient, owner: dict, db: Session) -> None:
    headers = {"Idempotency-Key": "expired-key"}
    client.post(f"{API_V1}/pets", json={"name": "Старый"}, headers=headers)

    stored = db.query(IdempotencyKey).one()
    stored.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()

    response = client.post(f"{API_V1}/pets", json={"name": "Новый"}, headers=headers)

    assert response.status_code == 201
    assert "Idempotent-Replay" not in response.headers
    assert len(client.get(f"{API_V1}/pets").json()) == 2


# --- Шифрование ------------------------------------------------------------


def test_owner_notes_are_encrypted_at_rest(client: TestClient, owner: dict, db: Session) -> None:
    response = client.post(
        f"{API_V1}/pets",
        json={"name": "Макс", "owner_notes": "Аллергия на курицу, хронический отит"},
    )
    pet_id = response.json()["id"]

    raw = db.execute(text("select owner_notes from pets where id = :id"), {"id": pet_id}).scalar_one()
    assert raw.startswith("enc:v1:")
    assert "Аллергия" not in raw

    # Через API значение возвращается расшифрованным.
    assert client.get(f"{API_V1}/pets/{pet_id}").json()["owner_notes"] == "Аллергия на курицу, хронический отит"


def test_chat_messages_are_encrypted_at_rest(client: TestClient, pet: dict, db: Session, monkeypatch) -> None:
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "ollama_base_url", "http://127.0.0.1:9")
    client.post(
        f"{API_V1}/chat/stream",
        json={"message": "У кота кровь в моче", "conversation_id": "enc-check", "pet_id": pet["id"]},
    )

    raw = db.execute(text("select content from chat_messages where conversation_id = 'enc-check'")).scalars().all()
    assert raw
    assert all(value.startswith("enc:v1:") for value in raw)
    assert not any("кровь" in value for value in raw)

    history = client.get(f"{API_V1}/chat/history/enc-check").json()
    assert history[0]["content"] == "У кота кровь в моче"


def test_legacy_plaintext_notes_are_readable(client: TestClient, owner: dict, db: Session) -> None:
    """Записи, сохранённые до включения шифрования, читаются как есть."""
    db.execute(
        text(
            "insert into pets (owner_id, name, species, owner_notes, medical_secret_token) "
            "values (:owner_id, 'Старый', 'dog', 'заметки открытым текстом', 'legacy-token-1234567890')"
        ),
        {"owner_id": owner["user"]["id"]},
    )
    db.commit()

    pets = client.get(f"{API_V1}/pets").json()

    assert pets[0]["owner_notes"] == "заметки открытым текстом"
