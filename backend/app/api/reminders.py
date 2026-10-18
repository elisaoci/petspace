"""Напоминания в приложении: что уже просрочено, что сегодня и что скоро.

Это серверный расчёт поверх календаря: приложение показывает список при открытии.
Фоновые push/email появятся вместе с очередью задач (Redis + Celery).
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import CalendarEvent, Pet

router = APIRouter(tags=["reminders"])

FINAL_STATUSES = {"done", "cancelled"}

REMINDER_OVERDUE = "overdue"
REMINDER_TODAY = "today"
REMINDER_SOON = "soon"


class ReminderResponse(BaseModel):
    event_id: int
    pet_id: int
    pet_name: str
    title: str
    event_type: str
    starts_at: datetime
    status: str


def _status(starts_at: datetime, now: datetime) -> str:
    if starts_at < now:
        return REMINDER_OVERDUE
    if starts_at.date() == now.date():
        return REMINDER_TODAY
    return REMINDER_SOON


@router.get("/reminders", response_model=list[ReminderResponse])
def list_reminders(
    user: CurrentUser,
    db: DbSession,
    days: int = Query(3, ge=1, le=30, description="Горизонт напоминаний в днях"),
) -> list[ReminderResponse]:
    """Просроченные события и ближайшие в пределах `days` дней, по всем питомцам владельца."""
    now = datetime.now(UTC)
    horizon = now + timedelta(days=days)

    rows = db.execute(
        select(CalendarEvent, Pet.name)
        .join(Pet, Pet.id == CalendarEvent.pet_id)
        .where(
            Pet.owner_id == user.id,
            CalendarEvent.status.not_in(FINAL_STATUSES),
            CalendarEvent.starts_at <= horizon,
        )
        .order_by(CalendarEvent.starts_at)
    ).all()

    return [
        ReminderResponse(
            event_id=event.id,
            pet_id=event.pet_id,
            pet_name=pet_name,
            title=event.title,
            event_type=event.event_type,
            starts_at=event.starts_at,
            status=_status(event.starts_at, now),
        )
        for event, pet_name in rows
    ]
