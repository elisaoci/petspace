from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import CalendarEvent
from tests.helpers import API_V1


def test_public_medical_card_hides_owner_notes(client: TestClient, pet: dict, db: Session) -> None:
    db.add_all(
        [
            CalendarEvent(
                pet_id=pet["id"],
                title="Вакцинация от бешенства",
                event_type="vaccine",
                starts_at=datetime.now(UTC) + timedelta(days=20),
            ),
            CalendarEvent(
                pet_id=pet["id"],
                title="Стрижка когтей",
                event_type="grooming",
                starts_at=datetime.now(UTC) + timedelta(days=5),
            ),
        ]
    )
    db.commit()
    # Медкарта по ссылке открывается без авторизации.
    client.headers.pop("Authorization")

    response = client.get(f"{API_V1}/pets/public/medical-card/{pet['medical_secret_token']}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == pet["name"]
    assert body["age_years"] is not None
    # Личные заметки владельца не должны попадать в публичную медкарту.
    assert "owner_notes" not in body
    assert "Аллергии" not in response.text
    # В публичную карту попадают только прививки.
    assert [item["title"] for item in body["vaccinations"]] == ["Вакцинация от бешенства"]


def test_unknown_medical_token_returns_404(client: TestClient) -> None:
    assert client.get(f"{API_V1}/pets/public/medical-card/no-such-token").status_code == 404


def test_renewed_token_invalidates_old_link(client: TestClient, pet: dict) -> None:
    old_token = pet["medical_secret_token"]
    new_token = client.post(f"{API_V1}/pets/{pet['id']}/medical-token").json()["medical_secret_token"]

    client.headers.pop("Authorization")
    assert client.get(f"{API_V1}/pets/public/medical-card/{old_token}").status_code == 404
    assert client.get(f"{API_V1}/pets/public/medical-card/{new_token}").status_code == 200
