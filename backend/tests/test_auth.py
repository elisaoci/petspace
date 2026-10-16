from fastapi.testclient import TestClient

from app.models import CONSENT_VERSIONS, REQUIRED_CONSENTS
from tests.helpers import API_V1, consents_payload, request_code, verify_code

EMAIL = "new-user@example.com"


def test_otp_request_returns_generic_message_and_expiry(client: TestClient, mailbox) -> None:
    response = client.post(f"{API_V1}/auth/otp/request", json={"email": EMAIL})

    assert response.status_code == 202
    body = response.json()
    assert body["expires_in"] > 0
    assert body["dev_code"] and len(body["dev_code"]) == 6
    # Письмо действительно ушло и в нём тот же код.
    assert mailbox.last_recipient() == EMAIL
    assert mailbox.last_code() == body["dev_code"]


def test_otp_request_validates_email(client: TestClient) -> None:
    assert client.post(f"{API_V1}/auth/otp/request", json={"email": "не-почта"}).status_code == 422


def test_otp_request_is_rate_limited(client: TestClient) -> None:
    for _ in range(3):
        assert client.post(f"{API_V1}/auth/otp/request", json={"email": EMAIL}).status_code == 202

    response = client.post(f"{API_V1}/auth/otp/request", json={"email": EMAIL})

    assert response.status_code == 429
    # Лимит считается по адресу: другой email не затронут.
    assert client.post(f"{API_V1}/auth/otp/request", json={"email": "other@example.com"}).status_code == 202


def test_verify_creates_user_and_returns_tokens(client: TestClient) -> None:
    code = request_code(client, EMAIL)

    result = verify_code(client, EMAIL, code)

    assert result["status_code"] == 200, result["body"]
    body = result["body"]
    assert body["access_token"] and body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == EMAIL
    assert body["user"]["role"] == "owner"
    assert body["user"]["consents_accepted"] is True


def test_verify_rejects_wrong_code_and_counts_attempts(client: TestClient) -> None:
    correct = request_code(client, EMAIL)

    wrong = verify_code(client, EMAIL, "000000" if correct != "000000" else "111111")
    assert wrong["status_code"] == 401

    # Правильный код после одной ошибки всё ещё работает.
    assert verify_code(client, EMAIL, correct)["status_code"] == 200


def test_verify_blocks_after_too_many_attempts(client: TestClient) -> None:
    correct = request_code(client, EMAIL)

    for _ in range(5):
        assert verify_code(client, EMAIL, "999999" if correct != "999999" else "888888")["status_code"] == 401

    response = client.post(f"{API_V1}/auth/otp/verify", json={"email": EMAIL, "code": correct})
    assert response.status_code == 429


def test_verify_requires_consents_for_new_user(client: TestClient) -> None:
    code = request_code(client, EMAIL)

    result = verify_code(client, EMAIL, code, accept_consents=False)

    # Регистрация без согласий отклоняется, код не расходуется.
    assert result["status_code"] == 422
    assert result["body"]["detail"]["error"] == "consent_required"
    assert verify_code(client, EMAIL, code)["status_code"] == 200


def test_verify_rejects_outdated_consent_version(client: TestClient) -> None:
    code = request_code(client, EMAIL)

    response = client.post(
        f"{API_V1}/auth/otp/verify",
        json={
            "email": EMAIL,
            "code": code,
            "consents": [{"kind": "terms", "version": "2000-01-01"}, {"kind": "privacy", "version": "2000-01-01"}],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "invalid_consents"


def test_code_cannot_be_reused(client: TestClient) -> None:
    code = request_code(client, EMAIL)
    assert verify_code(client, EMAIL, code)["status_code"] == 200

    assert verify_code(client, EMAIL, code)["status_code"] == 401


def test_me_requires_token_and_returns_user(client: TestClient, owner: dict) -> None:
    assert client.get(f"{API_V1}/auth/me").status_code == 200
    assert client.get(f"{API_V1}/auth/me").json()["email"] == owner["user"]["email"]

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
    assert rotated["access_token"]

    # Новая пара работает.
    me = client.get(f"{API_V1}/auth/me", headers={"Authorization": f"Bearer {rotated['access_token']}"})
    assert me.status_code == 200


def test_refresh_reuse_revokes_all_sessions(client: TestClient, owner: dict) -> None:
    first = owner["refresh_token"]
    second = client.post(f"{API_V1}/auth/refresh", json={"refresh_token": first}).json()["refresh_token"]

    # Повторное использование старого токена — признак кражи.
    reuse = client.post(f"{API_V1}/auth/refresh", json={"refresh_token": first})
    assert reuse.status_code == 401

    # После этого не работает и актуальный токен: все сессии отозваны.
    assert client.post(f"{API_V1}/auth/refresh", json={"refresh_token": second}).status_code == 401


def test_logout_revokes_refresh_token(client: TestClient, owner: dict) -> None:
    response = client.post(f"{API_V1}/auth/logout", json={"refresh_token": owner["refresh_token"]})

    assert response.status_code == 204
    assert client.post(f"{API_V1}/auth/refresh", json={"refresh_token": owner["refresh_token"]}).status_code == 401


def test_pet_creation_requires_current_consents(client: TestClient, owner: dict, db) -> None:
    """Если согласие отозвано или версия текста устарела, создавать данные нельзя."""
    from app.models import Consent

    db.query(Consent).filter(Consent.user_id == owner["user"]["id"]).delete()
    db.commit()

    blocked = client.post(f"{API_V1}/pets", json={"name": "Без согласий"})
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["error"] == "consent_required"

    accepted = client.post(f"{API_V1}/auth/consents", json={"consents": consents_payload()})
    assert accepted.status_code == 201
    assert accepted.json()["consents_accepted"] is True

    assert client.post(f"{API_V1}/pets", json={"name": "Со согласиями"}).status_code == 201


def test_consents_endpoint_stores_version(client: TestClient, owner: dict, db) -> None:
    from app.models import Consent

    client.headers.pop("Authorization")
    response = client.post(
        f"{API_V1}/auth/consents",
        json={"consents": consents_payload()},
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    # Согласия уже приняты при регистрации — эндпоинт просто подтверждает их наличие.
    assert response.status_code == 201
    assert response.json()["consents_accepted"] is True
    stored = db.query(Consent).filter(Consent.user_id == owner["user"]["id"]).all()
    assert {item.kind for item in stored} == set(REQUIRED_CONSENTS)
    assert {item.version for item in stored} == set(CONSENT_VERSIONS.values())


def test_required_consents_are_exposed(client: TestClient) -> None:
    """Фронтенд берёт версии согласий из API, а не из своего кода."""
    response = client.get(f"{API_V1}/auth/consents/required")

    assert response.status_code == 200
    kinds = {item["kind"] for item in response.json()}
    assert kinds == set(REQUIRED_CONSENTS)
    assert all(item["version"] for item in response.json())


def test_audit_log_records_login_events(client: TestClient, owner: dict, db) -> None:
    from app.models import AuditLog

    actions = {row.action for row in db.query(AuditLog).all()}

    assert "otp.request" in actions
    assert "user.registered" in actions
