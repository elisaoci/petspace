"""Проверки доступа: без токена нельзя, чужой питомец не виден, публичная медкарта остаётся публичной."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.models import AuditLog, CalendarEvent, Pet
from tests.helpers import API_V1, register_owner

SECOND_EMAIL = "second@example.com"


@pytest.fixture()
def stranger(client_factory) -> TestClient:
    """Второй владелец со своим токеном."""
    other = client_factory()
    register_owner(other, SECOND_EMAIL)
    return other


def test_protected_endpoints_require_token(client: TestClient) -> None:
    anonymous_calls = [
        ("GET", f"{API_V1}/pets", None),
        ("POST", f"{API_V1}/pets", {"name": "Кто-то"}),
        ("GET", f"{API_V1}/pets/1", None),
        ("DELETE", f"{API_V1}/pets/1", None),
        ("GET", f"{API_V1}/events", None),
        ("POST", f"{API_V1}/events", {"pet_id": 1, "title": "Прогулка", "starts_at": datetime.now(UTC).isoformat()}),
        ("GET", f"{API_V1}/chat/history/pet-1", None),
        ("POST", f"{API_V1}/chat/stream", {"message": "Привет", "pet_id": 1}),
        ("POST", f"{API_V1}/payments/demo", {"owner_id": "1", "plan": "premium"}),
        ("GET", f"{API_V1}/auth/me", None),
    ]

    for method, url, body in anonymous_calls:
        response = client.request(method, url, json=body)
        assert response.status_code == 401, f"{method} {url} вернул {response.status_code}"


def test_health_is_open_without_token(client: TestClient) -> None:
    assert client.get("/api/health").status_code == 200
    assert client.get(f"{API_V1}/health").status_code == 200


def test_owner_sees_only_own_pets(client: TestClient, stranger: TestClient, pet: dict) -> None:
    assert client.get(f"{API_V1}/pets").json()[0]["id"] == pet["id"]
    assert stranger.get(f"{API_V1}/pets").json() == []


def test_stranger_cannot_read_update_or_delete_pet(client: TestClient, stranger: TestClient, pet: dict) -> None:
    assert stranger.get(f"{API_V1}/pets/{pet['id']}").status_code == 404
    assert stranger.patch(f"{API_V1}/pets/{pet['id']}", json={"name": "Угнан"}).status_code == 404
    assert stranger.delete(f"{API_V1}/pets/{pet['id']}").status_code == 404
    assert stranger.post(f"{API_V1}/pets/{pet['id']}/medical-token").status_code == 404
    assert stranger.post(
        f"{API_V1}/pets/{pet['id']}/photo",
        files={"file": ("avatar.png", b"\x89PNG\r\n\x1a\n", "image/png")},
    ).status_code == 404

    # Данные владельца не изменились.
    assert client.get(f"{API_V1}/pets/{pet['id']}").json()["name"] == pet["name"]


def test_stranger_cannot_touch_events_of_foreign_pet(client: TestClient, stranger: TestClient, pet: dict) -> None:
    created = client.post(
        f"{API_V1}/events",
        json={
            "pet_id": pet["id"],
            "title": "Вакцинация",
            "event_type": "vaccine",
            "starts_at": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
        },
    ).json()

    assert stranger.get(f"{API_V1}/events").json() == []
    assert stranger.get(f"{API_V1}/events/{created['id']}").status_code == 404
    assert stranger.patch(f"{API_V1}/events/{created['id']}", json={"title": "Чужое"}).status_code == 404
    assert stranger.delete(f"{API_V1}/events/{created['id']}").status_code == 404
    assert stranger.post(
        f"{API_V1}/events",
        json={"pet_id": pet["id"], "title": "Новое", "starts_at": datetime.now(UTC).isoformat()},
    ).status_code == 404


def test_stranger_cannot_read_foreign_chat(client: TestClient, stranger: TestClient, pet: dict, monkeypatch) -> None:
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "ollama_base_url", "http://127.0.0.1:9")
    client.post(f"{API_V1}/chat/stream", json={"message": "Привет", "pet_id": pet["id"], "conversation_id": "shared"})

    assert client.get(f"{API_V1}/chat/history/shared").json() != []
    assert stranger.get(f"{API_V1}/chat/history/shared").json() == []
    assert stranger.post(
        f"{API_V1}/chat/stream",
        json={"message": "Чужой вопрос", "pet_id": pet["id"], "conversation_id": "shared"},
    ).status_code == 404


def test_public_medical_card_is_open_and_audited(client: TestClient, pet: dict, db) -> None:
    client.headers.pop("Authorization")

    response = client.get(f"{API_V1}/pets/public/medical-card/{pet['medical_secret_token']}")

    assert response.status_code == 200
    assert response.json()["name"] == pet["name"]
    actions = [row.action for row in db.query(AuditLog).all()]
    assert "medical_card.read" in actions


def test_deleting_pet_removes_its_events(client: TestClient, pet: dict, db) -> None:
    db.add(
        CalendarEvent(
            pet_id=pet["id"],
            title="Прогулка",
            event_type="walk",
            starts_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    db.commit()

    assert client.delete(f"{API_V1}/pets/{pet['id']}").status_code == 204

    assert client.get(f"{API_V1}/events").json() == []
    assert db.query(CalendarEvent).count() == 0
    assert db.query(Pet).count() == 0
