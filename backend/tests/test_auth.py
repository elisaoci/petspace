import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import CONSENT_VERSIONS, REQUIRED_CONSENTS, Consent, User
from tests.helpers import (
    API_V1,
    DEFAULT_PASSWORD,
    consents_payload,
    login,
    register,
    request_code,
    verify_code,
)

EMAIL = "new-user@example.com"


# --- Регистрация -----------------------------------------------------------


def test_register_creates_user_with_password_and_tokens(client: TestClient) -> None:
    result = register(client, EMAIL)

    assert result["status_code"] == 201, result["body"]
    body = result["body"]
    assert body["access_token"] and body["refresh_token"]
    assert body["user"]["email"] == EMAIL
    assert body["user"]["role"] == "owner"
    assert body["user"]["consents_accepted"] is True
    assert body["user"]["has_password"] is True


def test_register_requires_all_consents(client: TestClient) -> None:
    without_consents = client.post(
        f"{API_V1}/auth/register",
        json={"email": EMAIL, "password": DEFAULT_PASSWORD},
    )
    assert without_consents.status_code == 422

    # Только одно согласие из двух — тоже отказ, с указанием недостающего.
    partial = register(client, EMAIL, consents=[{"kind": "terms", "version": CONSENT_VERSIONS["terms"]}])
    assert partial["status_code"] == 422
    assert partial["body"]["detail"]["kinds"] == ["privacy"]


def test_register_rejects_outdated_consent_version(client: TestClient) -> None:
    result = register(
        client,
        EMAIL,
        consents=[
            {"kind": "terms", "version": "2000-01-01"},
            {"kind": "privacy", "version": "2000-01-01"},
        ],
    )

    assert result["status_code"] == 422
    assert result["body"]["detail"]["error"] == "invalid_consents"


def test_register_rejects_duplicate_email(client: TestClient) -> None:
    assert register(client, EMAIL)["status_code"] == 201

    duplicate = register(client, EMAIL, password="another-pass-123")

    assert duplicate["status_code"] == 409
    assert duplicate["body"]["detail"]["error"] == "email_taken"


def test_register_validates_password(client: TestClient) -> None:
    short = register(client, EMAIL, password="short1")
    assert short["status_code"] == 422

    trivial = register(client, EMAIL, password="aaaaaaaaaaa")
    assert trivial["status_code"] == 422


def test_register_accepts_normalized_email(client: TestClient) -> None:
    # Регистр и пробелы не должны создавать «разные» аккаунты на один адрес.
    assert register(client, "  Mixed@Example.COM ")["status_code"] == 201
    assert register(client, "mixed@example.com", password="another-pass-123")["status_code"] == 409


# --- Вход по паролю --------------------------------------------------------


def test_login_with_password(client: TestClient) -> None:
    register(client, EMAIL)

    result = login(client, EMAIL)

    assert result["status_code"] == 200, result["body"]
    assert result["body"]["access_token"]
    assert result["body"]["user"]["email"] == EMAIL


def test_login_rejects_wrong_password_with_generic_message(client: TestClient) -> None:
    register(client, EMAIL)

    wrong = login(client, EMAIL, "wrong-password-123")
    unknown = login(client, "nobody@example.com", "wrong-password-123")

    assert wrong["status_code"] == 401
    assert unknown["status_code"] == 401
    # Сообщения совпадают: по ответу нельзя узнать, существует ли аккаунт.
    assert wrong["body"]["detail"] == unknown["body"]["detail"]


def test_login_locks_account_after_failed_attempts(client: TestClient, db: Session) -> None:
    register(client, EMAIL)

    for _ in range(5):
        assert login(client, EMAIL, "wrong-password-123")["status_code"] == 401

    locked = login(client, EMAIL)
    assert locked["status_code"] == 429
    assert locked["body"]["detail"]

    user = db.query(User).filter(User.email == EMAIL).one()
    assert user.locked_until is not None


def test_login_resets_failed_attempts_after_success(client: TestClient, db: Session) -> None:
    register(client, EMAIL)

    for _ in range(2):
        assert login(client, EMAIL, "wrong-password-123")["status_code"] == 401
    assert login(client, EMAIL)["status_code"] == 200

    db.expire_all()
    user = db.query(User).filter(User.email == EMAIL).one()
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


def test_login_for_account_without_password_suggests_code(client: TestClient, db: Session) -> None:
    db.add(User(email="legacy@example.com", role="owner", status="active"))
    db.commit()

    result = login(client, "legacy@example.com", "whatever-123")

    assert result["status_code"] == 401
    assert result["body"]["detail"]["error"] == "password_not_set"


# --- Вход по коду (альтернатива паролю) ------------------------------------


def test_otp_login_works_for_existing_account(client: TestClient) -> None:
    register(client, EMAIL)

    code = request_code(client, EMAIL)
    result = verify_code(client, EMAIL, code)

    assert result["status_code"] == 200, result["body"]
    assert result["body"]["access_token"]


def test_otp_does_not_register_new_account(client: TestClient) -> None:
    code = request_code(client, "unknown@example.com")

    result = verify_code(client, "unknown@example.com", code)

    assert result["status_code"] == 404
    assert result["body"]["detail"]["error"] == "user_not_found"


def test_otp_code_is_not_returned_without_dev_flag(client: TestClient, monkeypatch) -> None:
    """Код входа не отдаётся в ответе, если флаг разработки выключен."""
    monkeypatch.setattr(get_settings(), "expose_dev_otp", False)

    response = client.post(f"{API_V1}/auth/otp/request", json={"email": "anyone@example.com"})

    assert response.status_code == 202
    assert response.json()["dev_code"] is None


def test_production_refuses_dev_otp_exposure() -> None:
    """Конфигурация с отдачей кода входа не должна подниматься в prod."""
    with pytest.raises(ValidationError):
        Settings(
            environment="prod",
            jwt_secret="x" * 40,
            expose_dev_otp=True,
        )


def test_otp_request_is_rate_limited(client: TestClient) -> None:
    register(client, EMAIL)

    for _ in range(3):
        assert client.post(f"{API_V1}/auth/otp/request", json={"email": EMAIL}).status_code == 202

    assert client.post(f"{API_V1}/auth/otp/request", json={"email": EMAIL}).status_code == 429
    # Лимит считается по адресу: другой email не затронут.
    assert client.post(f"{API_V1}/auth/otp/request", json={"email": "other@example.com"}).status_code == 202


def test_otp_rejects_wrong_code_and_counts_attempts(client: TestClient) -> None:
    register(client, EMAIL)
    correct = request_code(client, EMAIL)

    assert verify_code(client, EMAIL, "000000" if correct != "000000" else "111111")["status_code"] == 401
    assert verify_code(client, EMAIL, correct)["status_code"] == 200


def test_otp_blocks_after_too_many_attempts(client: TestClient) -> None:
    register(client, EMAIL)
    correct = request_code(client, EMAIL)

    for _ in range(5):
        assert verify_code(client, EMAIL, "999999" if correct != "999999" else "888888")["status_code"] == 401

    assert client.post(f"{API_V1}/auth/otp/verify", json={"email": EMAIL, "code": correct}).status_code == 429


def test_otp_code_cannot_be_reused(client: TestClient) -> None:
    register(client, EMAIL)
    code = request_code(client, EMAIL)

    assert verify_code(client, EMAIL, code)["status_code"] == 200
    assert verify_code(client, EMAIL, code)["status_code"] == 401


# --- Токены и сессии -------------------------------------------------------


def test_me_requires_token_and_returns_user(client: TestClient, owner: dict) -> None:
    response = client.get(f"{API_V1}/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == owner["user"]["email"]
    assert response.json()["has_password"] is True

    client.headers.pop("Authorization")
    assert client.get(f"{API_V1}/auth/me").status_code == 401


def test_me_rejects_garbage_token(client: TestClient) -> None:
    response = client.get(f"{API_V1}/auth/me", headers={"Authorization": "Bearer not-a-jwt"})

    assert response.status_code == 401


def test_refresh_rotates_tokens(client: TestClient, owner: dict) -> None:
    response = client.post(f"{API_V1}/auth/refresh", json={"refresh_token": owner["refresh_token"]})

    assert response.status_code == 200, response.text
    rotated = response.json()
    assert rotated["refresh_token"] != owner["refresh_token"]
    assert client.get(
        f"{API_V1}/auth/me", headers={"Authorization": f"Bearer {rotated['access_token']}"}
    ).status_code == 200


def test_refresh_reuse_revokes_all_sessions(client: TestClient, owner: dict) -> None:
    first = owner["refresh_token"]
    second = client.post(f"{API_V1}/auth/refresh", json={"refresh_token": first}).json()["refresh_token"]

    # Повторное использование старого токена — признак кражи.
    assert client.post(f"{API_V1}/auth/refresh", json={"refresh_token": first}).status_code == 401
    # После этого не работает и актуальный токен: все сессии отозваны.
    assert client.post(f"{API_V1}/auth/refresh", json={"refresh_token": second}).status_code == 401


def test_logout_revokes_refresh_token(client: TestClient, owner: dict) -> None:
    assert client.post(f"{API_V1}/auth/logout", json={"refresh_token": owner["refresh_token"]}).status_code == 204

    assert client.post(f"{API_V1}/auth/refresh", json={"refresh_token": owner["refresh_token"]}).status_code == 401


# --- Согласия --------------------------------------------------------------


def test_required_consents_are_exposed(client: TestClient) -> None:
    """Фронтенд берёт версии согласий из API, а не из своего кода."""
    response = client.get(f"{API_V1}/auth/consents/required")

    assert response.status_code == 200
    assert {item["kind"] for item in response.json()} == set(REQUIRED_CONSENTS)


def test_pet_creation_requires_current_consents(client: TestClient, owner: dict, db: Session) -> None:
    """Если согласие отозвано или версия текста устарела, создавать данные нельзя."""
    db.query(Consent).filter(Consent.user_id == owner["user"]["id"]).delete()
    db.commit()

    blocked = client.post(f"{API_V1}/pets", json={"name": "Без согласий"})
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["error"] == "consent_required"

    accepted = client.post(f"{API_V1}/auth/consents", json={"consents": consents_payload()})
    assert accepted.status_code == 201
    assert accepted.json()["consents_accepted"] is True

    assert client.post(f"{API_V1}/pets", json={"name": "Со согласиями"}).status_code == 201


# --- Аудит -----------------------------------------------------------------


def test_audit_log_records_auth_events(client: TestClient, owner: dict, db: Session) -> None:
    from app.models import AuditLog

    actions = {row.action for row in db.query(AuditLog).all()}

    assert "user.registered" in actions
