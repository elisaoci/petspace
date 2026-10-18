"""Оценка ответов ИИ, напоминания в приложении и удаление аккаунта."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import (
    AccessGrant,
    AuditLog,
    CalendarEvent,
    ChatMessage,
    MedicalRecord,
    Pet,
    User,
)
from tests.helpers import API_V1, DEFAULT_PASSWORD, login, register_owner


def _add_event(client: TestClient, pet_id: int, *, title: str, starts_at: datetime) -> dict:
    response = client.post(
        f"{API_V1}/events",
        json={"pet_id": pet_id, "title": title, "event_type": "vaccine", "starts_at": starts_at.isoformat()},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _ask_ai(client: TestClient, pet_id: int, message: str = "Сколько корма давать?") -> None:
    client.post(
        f"{API_V1}/chat/stream",
        json={"message": message, "conversation_id": "feedback-test", "pet_id": pet_id},
    )


# --- Оценка ответов ИИ -----------------------------------------------------


def test_feedback_on_assistant_message(client: TestClient, pet: dict, db: Session, monkeypatch) -> None:
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "ollama_base_url", "http://127.0.0.1:9")
    _ask_ai(client, pet["id"])

    # Модели нет, поэтому в истории только сообщение владельца — создаём ответ вручную.
    assistant = ChatMessage(
        pet_id=pet["id"], conversation_id="feedback-test", role="assistant", content="Ответ ИИ"
    )
    db.add(assistant)
    db.commit()

    response = client.post(
        f"{API_V1}/chat/messages/{assistant.id}/feedback", json={"value": "useful"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["feedback"] == "useful"
    assert client.get(f"{API_V1}/chat/history/feedback-test").json()[-1]["feedback"] == "useful"

    actions = [row.action for row in db.query(AuditLog).all()]
    assert "chat.feedback" in actions


def test_feedback_cannot_target_user_message(client: TestClient, pet: dict, db: Session) -> None:
    message = ChatMessage(pet_id=pet["id"], conversation_id="c1", role="user", content="Вопрос")
    db.add(message)
    db.commit()

    response = client.post(f"{API_V1}/chat/messages/{message.id}/feedback", json={"value": "useful"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "not_assistant_message"


def test_feedback_value_is_validated(client: TestClient, pet: dict, db: Session) -> None:
    message = ChatMessage(pet_id=pet["id"], conversation_id="c1", role="assistant", content="Ответ")
    db.add(message)
    db.commit()

    response = client.post(f"{API_V1}/chat/messages/{message.id}/feedback", json={"value": "great"})

    assert response.status_code == 422


def test_stranger_cannot_rate_foreign_answer(client: TestClient, client_factory, pet: dict, db: Session) -> None:
    message = ChatMessage(pet_id=pet["id"], conversation_id="c1", role="assistant", content="Ответ")
    db.add(message)
    db.commit()

    other = client_factory()
    register_owner(other, "stranger@example.com")

    assert other.post(f"{API_V1}/chat/messages/{message.id}/feedback", json={"value": "useful"}).status_code == 404


# --- Напоминания -----------------------------------------------------------


def test_reminders_include_overdue_today_and_soon(client: TestClient, pet: dict) -> None:
    now = datetime.now(UTC)
    _add_event(client, pet["id"], title="Просроченная прививка", starts_at=now - timedelta(days=2))
    _add_event(client, pet["id"], title="Сегодняшний приём", starts_at=now + timedelta(hours=2))
    _add_event(client, pet["id"], title="Приём через 2 дня", starts_at=now + timedelta(days=2))
    _add_event(client, pet["id"], title="Далеко в будущем", starts_at=now + timedelta(days=30))

    response = client.get(f"{API_V1}/reminders")

    assert response.status_code == 200, response.text
    rows = response.json()
    by_title = {row["title"]: row["status"] for row in rows}
    assert by_title["Просроченная прививка"] == "overdue"
    assert by_title["Сегодняшний приём"] == "today"
    assert by_title["Приём через 2 дня"] == "soon"
    assert "Далеко в будущем" not in by_title
    assert all(row["pet_name"] == pet["name"] for row in rows)


def test_reminders_skip_closed_events(client: TestClient, pet: dict) -> None:
    now = datetime.now(UTC)
    created = _add_event(client, pet["id"], title="Сделанная прививка", starts_at=now - timedelta(days=1))
    client.patch(f"{API_V1}/events/{created['id']}", json={"status": "done"})

    assert client.get(f"{API_V1}/reminders").json() == []


def test_reminders_horizon_is_configurable(client: TestClient, pet: dict) -> None:
    _add_event(client, pet["id"], title="Через 5 дней", starts_at=datetime.now(UTC) + timedelta(days=5))

    assert client.get(f"{API_V1}/reminders").json() == []
    assert len(client.get(f"{API_V1}/reminders", params={"days": 7}).json()) == 1
    assert client.get(f"{API_V1}/reminders", params={"days": 40}).status_code == 422


def test_reminders_are_isolated_between_owners(client: TestClient, client_factory, pet: dict) -> None:
    _add_event(client, pet["id"], title="Чужое событие", starts_at=datetime.now(UTC) + timedelta(hours=1))

    other = client_factory()
    register_owner(other, "stranger@example.com")

    assert other.get(f"{API_V1}/reminders").json() == []


# --- Удаление аккаунта -----------------------------------------------------


def test_account_deletion_removes_all_personal_data(client: TestClient, pet: dict, db: Session) -> None:
    client.post(
        f"{API_V1}/pets/{pet['id']}/records",
        json={"kind": "visit", "title": "Приём", "occurred_at": datetime.now(UTC).isoformat()},
    )
    client.post(f"{API_V1}/pets/{pet['id']}/access-grants", json={"label": "Клиника", "ttl_days": 7})
    _add_event(client, pet["id"], title="Прививка", starts_at=datetime.now(UTC) + timedelta(days=5))

    response = client.post(
        f"{API_V1}/account/delete", json={"confirm": True, "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 204, response.text
    db.expire_all()
    assert db.query(User).count() == 0
    assert db.query(Pet).count() == 0
    assert db.query(MedicalRecord).count() == 0
    assert db.query(AccessGrant).count() == 0
    assert db.query(CalendarEvent).count() == 0
    assert db.query(ChatMessage).count() == 0

    # Ни войти, ни воспользоваться старым токеном больше нельзя.
    client.headers.pop("Authorization")
    assert login(client, "owner@example.com", DEFAULT_PASSWORD)["status_code"] == 401


def test_account_deletion_keeps_anonymous_audit_record(client: TestClient, owner: dict, db: Session) -> None:
    assert client.post(f"{API_V1}/account/delete", json={"confirm": True, "password": DEFAULT_PASSWORD}).status_code == 204

    db.expire_all()
    row = db.query(AuditLog).filter(AuditLog.action == "account.deleted").one()
    assert row.actor_user_id is None
    assert row.details == {"reason": "user_request"}


def test_account_deletion_requires_confirmation(client: TestClient, owner: dict) -> None:
    response = client.post(f"{API_V1}/account/delete", json={"password": DEFAULT_PASSWORD})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "confirmation_required"
    # Аккаунт на месте.
    assert client.get(f"{API_V1}/auth/me").status_code == 200


def test_account_deletion_requires_correct_password(client: TestClient, owner: dict) -> None:
    response = client.post(f"{API_V1}/account/delete", json={"confirm": True, "password": "wrong-pass-123"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "wrong_password"
    assert client.get(f"{API_V1}/auth/me").status_code == 200


def test_account_deletion_requires_authentication(client: TestClient) -> None:
    assert client.post(f"{API_V1}/account/delete", json={"confirm": True}).status_code == 401


def test_account_deletion_clears_refresh_tokens(client: TestClient, owner: dict, db: Session) -> None:
    refresh_token = owner["refresh_token"]
    assert client.post(f"{API_V1}/account/delete", json={"confirm": True, "password": DEFAULT_PASSWORD}).status_code == 204

    assert client.post(f"{API_V1}/auth/refresh", json={"refresh_token": refresh_token}).status_code == 401
    assert db.execute(text("select count(*) from refresh_tokens")).scalar_one() == 0
