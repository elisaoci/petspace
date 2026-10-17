"""Общие фикстуры тестов: тестовая БД, клиент API, почтовый ящик и авторизованный владелец.

Тесты работают с настоящим PostgreSQL (та же СУБД, что в проде), но с отдельной базой:
по умолчанию `petspace_test`. Адрес переопределяется переменной `TEST_DATABASE_URL`.
"""

import os
import re
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app import models  # noqa: F401  — регистрирует таблицы в Base.metadata
from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from tests.helpers import register_owner

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://petspace:petspace@localhost:5433/petspace_test",
)

engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class FakeEmailSender:
    """Подменяет отправку писем: код входа виден тесту."""

    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def send(self, to: str, subject: str, text: str) -> None:
        self.messages.append({"to": to, "subject": subject, "text": text})

    def last_code(self) -> str:
        match = re.search(r"\b(\d{6})\b", self.messages[-1]["text"])
        assert match, "в письме нет кода входа"
        return match.group(1)

    def last_recipient(self) -> str:
        return self.messages[-1]["to"]


@pytest.fixture(scope="session", autouse=True)
def _require_database() -> None:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:  # pragma: no cover - инфраструктурная проверка
        pytest.fail(
            f"Нет подключения к тестовой БД {TEST_DATABASE_URL}: {exc}\n"
            "Поднимите Postgres (docker compose -p petspace up -d db) и создайте базу:\n"
            "  docker compose -p petspace exec db "
            "psql -U petspace -d postgres -c 'CREATE DATABASE petspace_test'"
        )


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestingSessionLocal() as session:
        yield session


@pytest.fixture()
def mailbox(monkeypatch) -> FakeEmailSender:
    sender = FakeEmailSender()
    # Роутер авторизации берёт отправителя через get_email_sender.
    monkeypatch.setattr("app.api.auth.get_email_sender", lambda: sender)
    return sender


@pytest.fixture()
def client_factory(db: Session, tmp_path, monkeypatch):
    """Создаёт клиентов API: одному тесту часто нужно два разных пользователя."""
    def make(authorization: str | None = None) -> TestClient:
        def override_get_db() -> Generator[Session, None, None]:
            yield db

        app.dependency_overrides[get_db] = override_get_db
        # Загрузки пишем во временную папку, а не в backend/uploads.
        monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))
        test_client = TestClient(app)
        if authorization:
            test_client.headers["Authorization"] = authorization
        return test_client

    yield make
    app.dependency_overrides.clear()


@pytest.fixture()
def client(client_factory) -> TestClient:
    return client_factory()


@pytest.fixture(autouse=True)
def _fast_password_hashing(monkeypatch) -> None:
    """Тесты не должны платить за 600 000 итераций PBKDF2 на каждую регистрацию."""
    monkeypatch.setattr(get_settings(), "password_iterations", 1_000)


@pytest.fixture()
def owner(client: TestClient) -> dict:
    """Зарегистрированный владелец. Заголовок Authorization остаётся на клиенте."""
    return register_owner(client)


@pytest.fixture()
def pet(client: TestClient, owner: dict) -> dict:
    response = client.post(
        "/api/v1/pets",
        json={
            "name": "Макс",
            "species": "dog",
            "breed": "Золотистый ретривер",
            "birth_date": "2018-04-12",
            "sex": "male",
            "weight_kg": 32,
            "height_cm": 58,
            "owner_notes": "Аллергии: не выявлены",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()
