"""Поля профиля из ТЗ и заявки на приём."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.helpers import API_V1, register_owner

# --- Поля профиля ----------------------------------------------------------


def test_profile_stores_allergies_and_chronic_conditions(client: TestClient, pet: dict) -> None:
    response = client.patch(
        f"{API_V1}/pets/{pet['id']}",
        json={"allergies": "Курица, пыльца", "chronic_conditions": "Хронический отит"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allergies"] == "Курица, пыльца"
    assert body["chronic_conditions"] == "Хронический отит"
    # Заметки владельца остались нетронутыми.
    assert body["owner_notes"] == pet["owner_notes"]


def test_profile_medical_fields_are_encrypted(client: TestClient, pet: dict, db: Session) -> None:
    client.patch(
        f"{API_V1}/pets/{pet['id']}",
        json={"allergies": "Пенициллин", "chronic_conditions": "Диабет"},
    )

    raw = db.execute(
        text("select allergies, chronic_conditions from pets where id = :id"), {"id": pet["id"]}
    ).one()
    assert raw.allergies.startswith("enc:v1:")
    assert raw.chronic_conditions.startswith("enc:v1:")
    assert "Пенициллин" not in raw.allergies

    fetched = client.get(f"{API_V1}/pets/{pet['id']}").json()
    assert fetched["allergies"] == "Пенициллин"
    assert fetched["chronic_conditions"] == "Диабет"


def test_public_medical_card_shows_allergies_but_not_notes(client: TestClient, pet: dict) -> None:
    client.patch(
        f"{API_V1}/pets/{pet['id']}",
        json={"allergies": "Курица", "chronic_conditions": "Отит", "owner_notes": "Личное: не показывать"},
    )

    client.headers.pop("Authorization")
    body = client.get(f"{API_V1}/pets/public/medical-card/{pet['medical_secret_token']}").json()

    assert body["allergies"] == "Курица"
    assert body["chronic_conditions"] == "Отит"
    assert "owner_notes" not in body


def test_clinic_access_card_shows_allergies(client: TestClient, pet: dict) -> None:
    client.patch(f"{API_V1}/pets/{pet['id']}", json={"allergies": "Курица"})
    grant = client.post(
        f"{API_V1}/pets/{pet['id']}/access-grants", json={"label": "Клиника", "ttl_days": 3}
    ).json()

    client.headers.pop("Authorization")
    body = client.get(f"{API_V1}/medical/access/{grant['token']}").json()

    assert body["pet"]["allergies"] == "Курица"


# --- Запись на приём -------------------------------------------------------


def _slot(days: int = 2) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


def test_create_appointment(client: TestClient, pet: dict) -> None:
    response = client.post(
        f"{API_V1}/pets/{pet['id']}/appointments",
        json={"clinic_name": "Клиника «Айболит»", "slot_start": _slot(), "comment": "Беспокоит ухо"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "requested"
    assert body["clinic_name"] == "Клиника «Айболит»"

    listed = client.get(f"{API_V1}/pets/{pet['id']}/appointments")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == body["id"]


def test_appointment_in_the_past_is_rejected(client: TestClient, pet: dict) -> None:
    response = client.post(
        f"{API_V1}/pets/{pet['id']}/appointments",
        json={"clinic_name": "Клиника", "slot_start": (datetime.now(UTC) - timedelta(hours=1)).isoformat()},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "slot_in_past"


def test_cancel_appointment(client: TestClient, pet: dict) -> None:
    created = client.post(
        f"{API_V1}/pets/{pet['id']}/appointments",
        json={"clinic_name": "Клиника", "slot_start": _slot()},
    ).json()

    cancelled = client.post(f"{API_V1}/appointments/{created['id']}/cancel")

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


def test_appointment_comment_is_encrypted(client: TestClient, pet: dict, db: Session) -> None:
    created = client.post(
        f"{API_V1}/pets/{pet['id']}/appointments",
        json={"clinic_name": "Клиника", "slot_start": _slot(), "comment": "Кровь в моче"},
    ).json()

    raw = db.execute(
        text("select comment from appointments where id = :id"), {"id": created["id"]}
    ).scalar_one()
    assert raw.startswith("enc:v1:")
    assert "Кровь" not in raw


def test_stranger_cannot_see_or_cancel_appointments(client: TestClient, client_factory, pet: dict) -> None:
    created = client.post(
        f"{API_V1}/pets/{pet['id']}/appointments",
        json={"clinic_name": "Клиника", "slot_start": _slot()},
    ).json()

    other = client_factory()
    register_owner(other, "stranger@example.com")

    assert other.get(f"{API_V1}/pets/{pet['id']}/appointments").status_code == 404
    assert other.post(f"{API_V1}/appointments/{created['id']}/cancel").status_code == 404


def test_appointments_require_authentication(client: TestClient, pet: dict) -> None:
    client.headers.pop("Authorization")

    assert client.get(f"{API_V1}/pets/{pet['id']}/appointments").status_code == 401
