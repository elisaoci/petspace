"""Хелперы тестов: регистрация, вход и работа с токенами."""

from fastapi.testclient import TestClient

from app.models import CONSENT_VERSIONS, REQUIRED_CONSENTS

API_V1 = "/api/v1"
DEFAULT_EMAIL = "owner@example.com"
DEFAULT_PASSWORD = "secret-pass-123"


def consents_payload() -> list[dict]:
    return [{"kind": kind, "version": CONSENT_VERSIONS[kind]} for kind in REQUIRED_CONSENTS]


def _body(response) -> dict | None:
    return response.json() if response.content else None


def register(
    client: TestClient,
    email: str = DEFAULT_EMAIL,
    password: str = DEFAULT_PASSWORD,
    *,
    consents: list[dict] | None = None,
) -> dict:
    payload: dict = {"email": email, "password": password}
    if consents is not None:
        payload["consents"] = consents
    else:
        payload["consents"] = consents_payload()
    response = client.post(f"{API_V1}/auth/register", json=payload)
    return {"status_code": response.status_code, "body": _body(response)}


def register_owner(
    client: TestClient,
    email: str = DEFAULT_EMAIL,
    password: str = DEFAULT_PASSWORD,
) -> dict:
    """Регистрирует владельца и ставит заголовок Authorization на клиента."""
    result = register(client, email, password)
    assert result["status_code"] == 201, result["body"]
    tokens = result["body"]
    client.headers["Authorization"] = f"Bearer {tokens['access_token']}"
    return tokens


def login(client: TestClient, email: str = DEFAULT_EMAIL, password: str = DEFAULT_PASSWORD) -> dict:
    response = client.post(f"{API_V1}/auth/login", json={"email": email, "password": password})
    return {"status_code": response.status_code, "body": _body(response)}


def login_owner(
    client: TestClient,
    email: str = DEFAULT_EMAIL,
    password: str = DEFAULT_PASSWORD,
) -> dict:
    result = login(client, email, password)
    assert result["status_code"] == 200, result["body"]
    tokens = result["body"]
    client.headers["Authorization"] = f"Bearer {tokens['access_token']}"
    return tokens


def request_code(client: TestClient, email: str = DEFAULT_EMAIL) -> str:
    response = client.post(f"{API_V1}/auth/otp/request", json={"email": email})
    assert response.status_code == 202, response.text
    body = response.json()
    # Вне prod код возвращается в ответе — на этом и построен тест.
    assert body["dev_code"], "в тестовом окружении код должен возвращаться"
    return body["dev_code"]


def verify_code(client: TestClient, email: str, code: str) -> dict:
    response = client.post(f"{API_V1}/auth/otp/verify", json={"email": email, "code": code})
    return {"status_code": response.status_code, "body": _body(response)}


def auth_headers(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}
