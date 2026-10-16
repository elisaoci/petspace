"""Хелперы тестов: вход по коду и работа с токенами."""

from fastapi.testclient import TestClient

from app.models import CONSENT_VERSIONS, REQUIRED_CONSENTS

API_V1 = "/api/v1"
DEFAULT_EMAIL = "owner@example.com"


def consents_payload() -> list[dict]:
    return [{"kind": kind, "version": CONSENT_VERSIONS[kind]} for kind in REQUIRED_CONSENTS]


def request_code(client: TestClient, email: str = DEFAULT_EMAIL) -> str:
    response = client.post(f"{API_V1}/auth/otp/request", json={"email": email})
    assert response.status_code == 202, response.text
    body = response.json()
    # Вне prod код возвращается в ответе — на этом и построен тест.
    assert body["dev_code"], "в тестовом окружении код должен возвращаться"
    return body["dev_code"]


def verify_code(
    client: TestClient,
    email: str,
    code: str,
    *,
    accept_consents: bool = True,
) -> dict:
    payload: dict = {"email": email, "code": code}
    if accept_consents:
        payload["consents"] = consents_payload()
    response = client.post(f"{API_V1}/auth/otp/verify", json=payload)
    return {"status_code": response.status_code, "body": response.json() if response.content else None}


def login(
    client: TestClient,
    email: str = DEFAULT_EMAIL,
    *,
    accept_consents: bool = True,
) -> dict:
    """Полный вход: запрос кода, подтверждение и установка заголовка Authorization."""
    code = request_code(client, email)
    result = verify_code(client, email, code, accept_consents=accept_consents)
    assert result["status_code"] == 200, result["body"]
    tokens = result["body"]
    client.headers["Authorization"] = f"Bearer {tokens['access_token']}"
    return tokens


def auth_headers(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}
