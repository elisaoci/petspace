"""Общие фикстуры тестов: тестовая БД, клиент API.

Тесты работают с настоящим PostgreSQL (та же СУБД, что в проде), но с отдельной базой:
по умолчанию `petspace_test`. Адрес переопределяется переменной `TEST_DATABASE_URL`.
"""

import os
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

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://petspace:petspace@localhost:5433/petspace_test",
)

engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


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
def client(db: Session, tmp_path, monkeypatch) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    # Загрузки пишем во временную папку, а не в backend/uploads.
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def pet(client: TestClient) -> dict:
    response = client.post(
        "/api/pets",
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
