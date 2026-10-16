from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, get_owned_pet
from app.models import CalendarEvent, Pet
from app.schemas.events import EventCreate, EventResponse, EventUpdate

router = APIRouter(prefix="/events", tags=["events"])

FINAL_STATUSES = {"done", "cancelled"}


def _response(event: CalendarEvent) -> EventResponse:
    computed = event.status
    if event.status not in FINAL_STATUSES and event.starts_at < datetime.now(UTC):
        computed = "overdue"
    return EventResponse.model_validate({**{c.name: getattr(event, c.name) for c in CalendarEvent.__table__.columns}, "computed_status": computed})


def _owned_event(event_id: int, user: CurrentUser, db: DbSession) -> CalendarEvent:
    """Событие доступно, только если его питомец принадлежит текущему пользователю."""
    event = db.scalar(
        select(CalendarEvent)
        .join(Pet, Pet.id == CalendarEvent.pet_id)
        .where(CalendarEvent.id == event_id, Pet.owner_id == user.id)
    )
    if event is None:
        raise HTTPException(404, "Event not found")
    return event


@router.get("", response_model=list[EventResponse])
def list_events(user: CurrentUser, db: DbSession, pet_id: int | None = None):
    query = (
        select(CalendarEvent)
        .join(Pet, Pet.id == CalendarEvent.pet_id)
        .where(Pet.owner_id == user.id)
        .order_by(CalendarEvent.starts_at)
    )
    if pet_id is not None:
        query = query.where(CalendarEvent.pet_id == pet_id)
    return [_response(e) for e in db.scalars(query).all()]


@router.post("", response_model=EventResponse, status_code=201)
def create_event(payload: EventCreate, user: CurrentUser, db: DbSession):
    get_owned_pet(payload.pet_id, user, db)
    event = CalendarEvent(**payload.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return _response(event)


@router.get("/{event_id}", response_model=EventResponse)
def get_event(event_id: int, user: CurrentUser, db: DbSession):
    return _response(_owned_event(event_id, user, db))


@router.patch("/{event_id}", response_model=EventResponse)
def update_event(event_id: int, payload: EventUpdate, user: CurrentUser, db: DbSession):
    event = _owned_event(event_id, user, db)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(event, key, value)
    db.commit()
    db.refresh(event)
    return _response(event)


@router.delete("/{event_id}", status_code=204)
def delete_event(event_id: int, user: CurrentUser, db: DbSession):
    event = _owned_event(event_id, user, db)
    db.delete(event)
    db.commit()
