"""Аналитика экранов: приём событий, лимиты и сводка для админа."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import ROLE_PLATFORM_ADMIN, AnalyticsEvent, User
from tests.helpers import API_V1, register_owner


def _events(count: int) -> dict:
    return {
        "events": [
            {"name": "page_view", "path": f"/app/{index}", "occurred_at": "2026-10-16T10:00:00Z"}
            for index in range(count)
        ]
    }


def test_events_are_accepted(client: TestClient, owner: dict, db: Session) -> None:
    response = client.post(f"{API_V1}/analytics/events", json=_events(3))

    assert response.status_code == 202, response.text
    assert response.json()["accepted"] == 3
    stored = db.query(AnalyticsEvent).all()
    assert len(stored) == 3
    assert {row.user_id for row in stored} == {owner["user"]["id"]}


def test_batch_size_is_limited(client: TestClient, owner: dict) -> None:
    assert client.post(f"{API_V1}/analytics/events", json=_events(20)).status_code == 202
    assert client.post(f"{API_V1}/analytics/events", json=_events(21)).status_code == 422


def test_empty_batch_is_rejected(client: TestClient, owner: dict) -> None:
    assert client.post(f"{API_V1}/analytics/events", json={"events": []}).status_code == 422


def test_events_require_authentication(client: TestClient) -> None:
    assert client.post(f"{API_V1}/analytics/events", json=_events(1)).status_code == 401


def test_summary_is_admin_only(client: TestClient, owner: dict) -> None:
    client.post(f"{API_V1}/analytics/events", json=_events(2))

    assert client.get(f"{API_V1}/admin/analytics").status_code == 403


def test_summary_counts_events_by_name(client: TestClient, owner: dict, db: Session) -> None:
    db.get(User, owner["user"]["id"]).role = ROLE_PLATFORM_ADMIN
    db.commit()
    client.post(f"{API_V1}/analytics/events", json=_events(2))
    client.post(
        f"{API_V1}/analytics/events",
        json={"events": [{"name": "chat_message_sent", "path": "/app/chat"}]},
    )

    response = client.get(f"{API_V1}/admin/analytics", params={"days": 7})

    assert response.status_code == 200, response.text
    counts = {row["name"]: row["count"] for row in response.json()}
    assert counts["page_view"] == 2
    assert counts["chat_message_sent"] == 1


def test_events_are_isolated_between_users(client: TestClient, client_factory, owner: dict, db: Session) -> None:
    client.post(f"{API_V1}/analytics/events", json=_events(1))
    other = client_factory()
    register_owner(other, "other@example.com")
    other.post(f"{API_V1}/analytics/events", json=_events(1))

    user_ids = {row.user_id for row in db.query(AnalyticsEvent).all()}
    assert len(user_ids) == 2


def test_events_are_deleted_with_account(client: TestClient, owner: dict, db: Session) -> None:
    client.post(f"{API_V1}/analytics/events", json=_events(2))
    from tests.helpers import DEFAULT_PASSWORD

    assert client.post(
        f"{API_V1}/account/delete", json={"confirm": True, "password": DEFAULT_PASSWORD}
    ).status_code == 204

    db.expire_all()
    assert db.query(AnalyticsEvent).count() == 0
