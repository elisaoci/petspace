from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, get_owned_pet
from app.api.pagination import PaginationParams, pagination_headers
from app.models import CalendarEvent, Pet
from app.schemas.events import EventCreate, EventResponse, EventUpdate
from app.services.idempotency import IDEMPOTENCY_HEADER, replay_response, store_response

router = APIRouter(prefix="/events", tags=["events"])

FINAL_STATUSES = {"done", "cancelled"}
ENDPOINT_CREATE = "POST /events"


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
def list_events(
    user: CurrentUser,
    pagination: PaginationParams,
    response: Response,
    db: DbSession,
    pet_id: int | None = None,
):
    conditions = [Pet.owner_id == user.id]
    if pet_id is not None:
        conditions.append(CalendarEvent.pet_id == pet_id)

    total = db.scalar(
        select(func.count())
        .select_from(CalendarEvent)
        .join(Pet, Pet.id == CalendarEvent.pet_id)
        .where(*conditions)
    ) or 0
    rows = db.scalars(
        select(CalendarEvent)
        .join(Pet, Pet.id == CalendarEvent.pet_id)
        .where(*conditions)
        .order_by(CalendarEvent.starts_at)
        .limit(pagination.limit)
        .offset(pagination.offset)
    ).all()
    pagination_headers(response, total=total, pagination=pagination)
    return [_response(e) for e in rows]


@router.post("", response_model=EventResponse, status_code=201)
def create_event(payload: EventCreate, request: Request, user: CurrentUser, db: DbSession):
    get_owned_pet(payload.pet_id, user, db)

    idempotency_key = request.headers.get(IDEMPOTENCY_HEADER)
    payload_data = payload.model_dump(mode="json")
    if idempotency_key:
        replayed = replay_response(
            db, user_id=user.id, key=idempotency_key, endpoint=ENDPOINT_CREATE, payload=payload_data
        )
        if replayed is not None:
            return replayed

    event = CalendarEvent(**payload.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)

    body = _response(event).model_dump(mode="json")
    if idempotency_key:
        store_response(
            db,
            user_id=user.id,
            key=idempotency_key,
            endpoint=ENDPOINT_CREATE,
            payload=payload_data,
            status_code=201,
            body=body,
        )
    return body


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
