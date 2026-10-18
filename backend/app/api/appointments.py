"""Запись на приём: владелец оставляет заявку, клиника подтверждает (этап 3).

Пока клиник в системе нет, заявка адресуется названию клиники и времени.
Отмена доступна владельцу в любой момент, статус заявки виден в списке.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, get_owned_pet
from app.api.pagination import PaginationParams, pagination_headers
from app.models import APPOINTMENT_CANCELLED, APPOINTMENT_REQUESTED, Appointment, Pet
from app.schemas.appointments import AppointmentCreate, AppointmentResponse
from app.services.audit import record_audit

router = APIRouter(tags=["appointments"])


def _owned_appointment(appointment_id: int, user: CurrentUser, db: DbSession) -> Appointment:
    appointment = db.scalar(
        select(Appointment)
        .join(Pet, Pet.id == Appointment.pet_id)
        .where(Appointment.id == appointment_id, Pet.owner_id == user.id)
    )
    if appointment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return appointment


@router.get("/pets/{pet_id}/appointments", response_model=list[AppointmentResponse])
def list_appointments(
    pet_id: int,
    user: CurrentUser,
    pagination: PaginationParams,
    response: Response,
    db: DbSession,
):
    get_owned_pet(pet_id, user, db)
    rows = db.scalars(
        select(Appointment)
        .where(Appointment.pet_id == pet_id)
        .order_by(Appointment.slot_start.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    ).all()
    pagination_headers(response, total=len(rows), pagination=pagination)
    return list(rows)


@router.post(
    "/pets/{pet_id}/appointments",
    response_model=AppointmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_appointment(
    pet_id: int, payload: AppointmentCreate, request: Request, user: CurrentUser, db: DbSession
):
    get_owned_pet(pet_id, user, db)

    slot = payload.slot_start
    if slot.tzinfo is None:
        slot = slot.replace(tzinfo=UTC)
    if slot <= datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "slot_in_past", "message": "Выберите время в будущем"},
        )

    appointment = Appointment(
        pet_id=pet_id,
        clinic_name=payload.clinic_name,
        slot_start=slot,
        comment=payload.comment,
        status=APPOINTMENT_REQUESTED,
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)

    record_audit(
        db,
        action="appointment.requested",
        actor_user_id=user.id,
        entity="appointment",
        entity_id=appointment.id,
        request=request,
        details={"pet_id": pet_id, "clinic": appointment.clinic_name},
    )
    return appointment


@router.post("/appointments/{appointment_id}/cancel", response_model=AppointmentResponse)
def cancel_appointment(
    appointment_id: int, request: Request, user: CurrentUser, db: DbSession
):
    appointment = _owned_appointment(appointment_id, user, db)
    if appointment.status != APPOINTMENT_CANCELLED:
        appointment.status = APPOINTMENT_CANCELLED
        db.commit()
        db.refresh(appointment)
        record_audit(
            db,
            action="appointment.cancelled",
            actor_user_id=user.id,
            entity="appointment",
            entity_id=appointment.id,
            request=request,
        )
    return appointment
