"""Аналитика экранов: приём событий от приложения и сводка для админа.

События шлёт клиент пакетами; хранится только имя события, путь и время.
Сводка доступна роли platform_admin — по ней видно воронку пилота.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, PlatformAdmin
from app.models import AnalyticsEvent

router = APIRouter(tags=["analytics"])

MAX_BATCH = 20


class ScreenEventIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    path: str = Field(min_length=1, max_length=255)
    occurred_at: datetime | None = None


class ScreenEventsPayload(BaseModel):
    events: list[ScreenEventIn] = Field(min_length=1, max_length=MAX_BATCH)


class ScreenEventsAccepted(BaseModel):
    accepted: int


class AnalyticsCount(BaseModel):
    name: str
    count: int


@router.post("/analytics/events", response_model=ScreenEventsAccepted, status_code=202)
def ingest_events(payload: ScreenEventsPayload, user: CurrentUser, db: DbSession) -> ScreenEventsAccepted:
    """Принимает пачку событий экранов. Ничего, кроме имени и пути, не сохраняем."""
    db.add_all(
        [
            AnalyticsEvent(
                user_id=user.id,
                name=event.name,
                path=event.path,
                occurred_at=event.occurred_at,
            )
            for event in payload.events
        ]
    )
    db.commit()
    return ScreenEventsAccepted(accepted=len(payload.events))


@router.get("/admin/analytics", response_model=list[AnalyticsCount])
def analytics_summary(
    admin: PlatformAdmin,
    db: DbSession,
    days: int = Query(7, ge=1, le=90, description="За сколько дней считать"),
) -> list[AnalyticsCount]:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = db.execute(
        select(AnalyticsEvent.name, func.count())
        .where(AnalyticsEvent.created_at >= since)
        .group_by(AnalyticsEvent.name)
        .order_by(func.count().desc())
    ).all()
    return [AnalyticsCount(name=name, count=count) for name, count in rows]
