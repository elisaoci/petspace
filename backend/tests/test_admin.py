"""Роли и админка платформы."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import cli
from app.models import ROLE_OWNER, ROLE_PLATFORM_ADMIN, User
from tests.helpers import API_V1


def test_owner_cannot_access_admin_endpoints(client: TestClient, owner: dict) -> None:
    response = client.get(f"{API_V1}/admin/audit")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "role_required"
    assert response.json()["error"]["details"]["required"] == [ROLE_PLATFORM_ADMIN]


def test_admin_sees_audit_log(client: TestClient, owner: dict, db: Session) -> None:
    user = db.get(User, owner["user"]["id"])
    user.role = ROLE_PLATFORM_ADMIN
    db.commit()

    response = client.get(f"{API_V1}/admin/audit", params={"limit": 5})

    assert response.status_code == 200, response.text
    assert response.headers["X-Total-Count"]
    assert isinstance(response.json(), list)
    assert any(row["action"] == "user.registered" for row in response.json())


def test_admin_sees_users(client: TestClient, owner: dict, db: Session) -> None:
    db.get(User, owner["user"]["id"]).role = ROLE_PLATFORM_ADMIN
    db.commit()

    response = client.get(f"{API_V1}/admin/users")

    assert response.status_code == 200
    assert response.json()[0]["email"] == owner["user"]["email"]


def test_cli_promote_grants_admin(db: Session, owner: dict) -> None:
    user = cli.promote(db, owner["user"]["email"].upper())

    assert user is not None
    assert user.role == ROLE_PLATFORM_ADMIN


def test_cli_promote_reports_unknown_user(db: Session) -> None:
    assert cli.promote(db, "nobody@example.com") is None


def test_cli_backfill_encrypts_legacy_rows(db: Session, owner: dict, client: TestClient) -> None:
    from sqlalchemy import text

    db.execute(
        text(
            "insert into pets (owner_id, name, species, owner_notes, medical_secret_token) "
            "values (:owner_id, 'Легаси', 'cat', 'хронический гастрит', 'legacy-backfill-token')"
        ),
        {"owner_id": owner["user"]["id"]},
    )
    db.commit()

    pets_updated, messages_updated = cli.backfill_encryption(db)

    assert pets_updated == 1
    assert messages_updated == 0
    raw = db.execute(text("select owner_notes from pets where name = 'Легаси'")).scalar_one()
    assert raw.startswith("enc:v1:")
    assert "гастрит" not in raw
    # И значение по-прежнему читается через API.
    pets = client.get(f"{API_V1}/pets").json()
    assert any(pet["owner_notes"] == "хронический гастрит" for pet in pets)


def test_production_requires_encryption_key() -> None:
    import pytest
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(environment="prod", jwt_secret="x" * 40, medical_encryption_key=None)

    # С корректным ключом конфигурация проходит.
    settings = Settings(
        environment="prod",
        jwt_secret="x" * 40,
        medical_encryption_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    )
    assert settings.environment == "prod"


def test_role_constants_include_clinic_roles() -> None:
    from app.models import (
        ROLE_CLINIC_ADMIN,
        ROLE_CLINIC_DOCTOR,
        ROLE_CLINIC_REGISTRAR,
        ROLES,
    )

    assert {ROLE_CLINIC_ADMIN, ROLE_CLINIC_DOCTOR, ROLE_CLINIC_REGISTRAR, ROLE_OWNER} <= set(ROLES)
