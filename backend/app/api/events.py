from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import CalendarEvent, Pet
from app.schemas.events import EventCreate, EventResponse, EventUpdate

router = APIRouter(prefix="/events", tags=["events"])

def _response(event: CalendarEvent) -> EventResponse:
    computed = event.status
    if event.status not in {"done", "cancelled"} and event.starts_at < datetime.now(timezone.utc):
        computed = "overdue"
    return EventResponse.model_validate({**{c.name: getattr(event, c.name) for c in CalendarEvent.__table__.columns}, "computed_status": computed})

@router.get("", response_model=list[EventResponse])
def list_events(pet_id: int | None = None, db: Session = Depends(get_db)):
    query = select(CalendarEvent).order_by(CalendarEvent.starts_at)
    if pet_id is not None: query = query.where(CalendarEvent.pet_id == pet_id)
    return [_response(e) for e in db.scalars(query).all()]

@router.post("", response_model=EventResponse, status_code=201)
def create_event(payload: EventCreate, db: Session = Depends(get_db)):
    if not db.get(Pet, payload.pet_id): raise HTTPException(404, "Pet not found")
    event = CalendarEvent(**payload.model_dump())
    db.add(event); db.commit(); db.refresh(event)
    return _response(event)

@router.get("/{event_id}", response_model=EventResponse)
def get_event(event_id: int, db: Session = Depends(get_db)):
    event = db.get(CalendarEvent, event_id)
    if not event: raise HTTPException(404, "Event not found")
    return _response(event)

@router.patch("/{event_id}", response_model=EventResponse)
def update_event(event_id: int, payload: EventUpdate, db: Session = Depends(get_db)):
    event = db.get(CalendarEvent, event_id)
    if not event: raise HTTPException(404, "Event not found")
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(event, key, value)
    db.commit(); db.refresh(event)
    return _response(event)

@router.delete("/{event_id}", status_code=204)
def delete_event(event_id: int, db: Session = Depends(get_db)):
    event = db.get(CalendarEvent, event_id)
    if not event: raise HTTPException(404, "Event not found")
    db.delete(event); db.commit()
