"""Смена пароля из кабинета и восстановление по коду из письма."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import AuditLog, User
from tests.helpers import (
    API_V1,
    DEFAULT_EMAIL,
    DEFAULT_PASSWORD,
    confirm_password_reset,
    login,
    request_reset_code,
    verify_code,
)

NEW_PASSWORD = "brand-new-pass-9"


# --- Смена пароля ----------------------------------------------------------


def test_change_password_returns_new_tokens_and_replaces_old(client: TestClient, owner: dict) -> None:
    response = client.post(
        f"{API_V1}/auth/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 200, response.text
    assert response.json()["access_token"]

    assert login(client, DEFAULT_EMAIL, NEW_PASSWORD)["status_code"] == 200
    assert login(client, DEFAULT_EMAIL, DEFAULT_PASSWORD)["status_code"] == 401


def test_change_password_requires_current_password(client: TestClient, owner: dict) -> None:
    without_current = client.post(f"{API_V1}/auth/password", json={"new_password": NEW_PASSWORD})
    assert without_current.status_code == 422

    wrong_current = client.post(
        f"{API_V1}/auth/password",
        json={"current_password": "wrong-pass-123", "new_password": NEW_PASSWORD},
    )
    assert wrong_current.status_code == 401

    # Пароль не изменился.
    assert login(client, DEFAULT_EMAIL, DEFAULT_PASSWORD)["status_code"] == 200


def test_change_password_rejects_same_password(client: TestClient, owner: dict) -> None:
    response = client.post(
        f"{API_V1}/auth/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "password_reused"


def test_change_password_rejects_weak_password(client: TestClient, owner: dict) -> None:
    response = client.post(
        f"{API_V1}/auth/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": "aaaaaaaaaa"},
    )

    assert response.status_code == 422


def test_change_password_revokes_other_sessions(client: TestClient, owner: dict) -> None:
    old_refresh = owner["refresh_token"]

    assert client.post(
        f"{API_V1}/auth/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
    ).status_code == 200

    assert client.post(f"{API_V1}/auth/refresh", json={"refresh_token": old_refresh}).status_code == 401


def test_change_password_requires_authentication(client: TestClient) -> None:
    response = client.post(
        f"{API_V1}/auth/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 401


def test_account_without_password_can_set_one(client: TestClient, db: Session) -> None:
    """Аккаунты из ранних версий входят по коду и могут сразу задать пароль."""
    db.add(User(email="legacy@example.com", role="owner", status="active"))
    db.commit()

    from tests.helpers import request_code

    code = request_code(client, "legacy@example.com")
    login_result = verify_code(client, "legacy@example.com", code)
    assert login_result["status_code"] == 200
    access = login_result["body"]["access_token"]

    response = client.post(
        f"{API_V1}/auth/password",
        json={"new_password": NEW_PASSWORD},
        headers={"Authorization": f"Bearer {access}"},
    )

    assert response.status_code == 200, response.text
    assert login(client, "legacy@example.com", NEW_PASSWORD)["status_code"] == 200


# --- Восстановление пароля -------------------------------------------------


def test_password_reset_flow(client: TestClient, owner: dict) -> None:
    code = request_reset_code(client)

    result = confirm_password_reset(client, DEFAULT_EMAIL, code, NEW_PASSWORD)

    assert result["status_code"] == 200, result["body"]
    assert result["body"]["access_token"]
    assert login(client, DEFAULT_EMAIL, NEW_PASSWORD)["status_code"] == 200
    assert login(client, DEFAULT_EMAIL, DEFAULT_PASSWORD)["status_code"] == 401


def test_reset_request_does_not_reveal_accounts(client: TestClient) -> None:
    known = client.post(f"{API_V1}/auth/password/reset/request", json={"email": "registered@example.com"})
    unknown = client.post(f"{API_V1}/auth/password/reset/request", json={"email": "nobody@example.com"})

    assert known.status_code == unknown.status_code == 202
    assert known.json()["message"] == unknown.json()["message"]


def test_reset_for_unknown_email_cannot_be_confirmed(client: TestClient) -> None:
    result = confirm_password_reset(client, "nobody@example.com", "123456", NEW_PASSWORD)

    assert result["status_code"] == 401


def test_reset_code_cannot_be_reused(client: TestClient, owner: dict) -> None:
    code = request_reset_code(client)

    assert confirm_password_reset(client, DEFAULT_EMAIL, code, NEW_PASSWORD)["status_code"] == 200
    assert confirm_password_reset(client, DEFAULT_EMAIL, code, "another-pass-123")["status_code"] == 401


def test_reset_code_does_not_work_for_login(client: TestClient, owner: dict) -> None:
    """Код сброса не должен открывать сессию: у кодов разное назначение."""
    code = request_reset_code(client)

    assert verify_code(client, DEFAULT_EMAIL, code)["status_code"] == 401
    # И наоборот: код входа не сбрасывает пароль.
    assert confirm_password_reset(client, DEFAULT_EMAIL, code, NEW_PASSWORD)["status_code"] == 200


def test_reset_revokes_existing_sessions(client: TestClient, owner: dict) -> None:
    old_refresh = owner["refresh_token"]
    code = request_reset_code(client)

    assert confirm_password_reset(client, DEFAULT_EMAIL, code, NEW_PASSWORD)["status_code"] == 200
    assert client.post(f"{API_V1}/auth/refresh", json={"refresh_token": old_refresh}).status_code == 401


def test_reset_request_is_rate_limited(client: TestClient, owner: dict) -> None:
    for _ in range(3):
        assert client.post(f"{API_V1}/auth/password/reset/request", json={"email": DEFAULT_EMAIL}).status_code == 202

    assert client.post(f"{API_V1}/auth/password/reset/request", json={"email": DEFAULT_EMAIL}).status_code == 429


def test_password_events_are_audited(client: TestClient, owner: dict, db: Session) -> None:
    assert client.post(
        f"{API_V1}/auth/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
    ).status_code == 200
    code = request_reset_code(client)
    assert confirm_password_reset(client, DEFAULT_EMAIL, code, "third-password-77")["status_code"] == 200

    actions = {row.action for row in db.query(AuditLog).all()}
    assert "password.changed" in actions
    assert "password.reset.request" in actions
    assert "password.reset.completed" in actions
