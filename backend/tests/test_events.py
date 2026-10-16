from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import CalendarEvent, Pet
from tests.helpers import API_V1


def _payload(pet_id: int, starts_at: datetime, **overrides) -> dict:
    return {
        "pet_id": pet_id,
        "title": "Вакцинация",
        "event_type": "vaccine",
        "starts_at": starts_at.isoformat(),
        **overrides,
    }


def test_past_planned_event_is_overdue(client: TestClient, pet: dict) -> None:
    response = client.post(f"{API_V1}/events", json=_payload(pet["id"], datetime.now(UTC) - timedelta(days=3)))

    assert response.status_code == 201, response.text
    assert response.json()["computed_status"] == "overdue"


def test_future_event_is_planned(client: TestClient, pet: dict) -> None:
    response = client.post(f"{API_V1}/events", json=_payload(pet["id"], datetime.now(UTC) + timedelta(days=10)))

    assert response.json()["computed_status"] == "planned"


def test_finished_event_keeps_its_status(client: TestClient, pet: dict) -> None:
    response = client.post(
        f"{API_V1}/events",
        json=_payload(pet["id"], datetime.now(UTC) - timedelta(days=3), status="done"),
    )

    assert response.json()["computed_status"] == "done"


def test_event_list_can_be_filtered_by_pet(client: TestClient, pet: dict, owner: dict, db: Session) -> None:
    other = Pet(name="Рекс", species="dog", owner_id=owner["user"]["id"], medical_secret_token="token-rex-1234567890")
    db.add(other)
    db.commit()
    db.refresh(other)

    db.add_all(
        [
            CalendarEvent(
                pet_id=pet["id"],
                title="Прогулка",
                event_type="walk",
                starts_at=datetime.now(UTC) + timedelta(hours=2),
            ),
            CalendarEvent(
                pet_id=other.id,
                title="Прививка",
                event_type="vaccine",
                starts_at=datetime.now(UTC) + timedelta(days=3),
            ),
        ]
    )
    db.commit()

    response = client.get(f"{API_V1}/events", params={"pet_id": pet["id"]})

    assert response.status_code == 200
    assert [event["title"] for event in response.json()] == ["Прогулка"]


def test_create_event_for_unknown_pet_returns_404(client: TestClient, owner: dict) -> None:
    response = client.post(f"{API_V1}/events", json=_payload(999, datetime.now(UTC) + timedelta(days=1)))

    assert response.status_code == 404


def test_delete_event(client: TestClient, pet: dict) -> None:
    created = client.post(
        f"{API_V1}/events",
        json=_payload(pet["id"], datetime.now(UTC) + timedelta(days=1)),
    ).json()

    assert client.delete(f"{API_V1}/events/{created['id']}").status_code == 204
    assert client.get(f"{API_V1}/events/{created['id']}").status_code == 404
