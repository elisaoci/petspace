"""Доступ клиник глазами владельца: коды, входящие запросы, телефон для поиска.

Владелец всегда решает сам:

- создаёт короткий код (он же QR) и показывает его в клинике;
- видит запросы клиник, пришедшие по телефону, и подтверждает или отклоняет их;
- в любой момент отзывает уже выданный доступ обычным `POST /access-grants/{id}/revoke`:
  доступы клиник лежат в том же списке `GET /pets/{id}/access-grants`, у них заполнен `clinic_id`.

Чтобы клиника могла найти питомца по телефону, владелец указывает номер в `PUT /profile/phone`.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession, get_owned_pet
from app.api.pagination import PaginationParams, pagination_headers
from app.models import (
    CLINIC_APPROVED,
    REQUEST_APPROVED,
    REQUEST_DENIED,
    REQUEST_PENDING,
    AccessCode,
    AccessRequest,
    Clinic,
    Pet,
    User,
)
from app.schemas.patient_access import (
    AccessCodeCreate,
    AccessCodeCreated,
    AccessCodeResponse,
    AccessRequestApprove,
    ClinicBrief,
    OwnerAccessRequest,
    PetBrief,
    PhonePayload,
    PhoneResponse,
    RequestStatusFilter,
)
from app.services.audit import record_audit
from app.services.patient_access import (
    CODE_TTL_MINUTES,
    format_code,
    generate_code,
    grant_clinic_access,
    hash_code,
    ordered_scopes,
    request_status_condition,
)

router = APIRouter(tags=["access"])


def _error(http_status: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"error": code, "message": message, **extra})


# --- Телефон для поиска клиникой ----------------------------------------------------------


@router.put("/profile/phone", response_model=PhoneResponse)
def set_phone(payload: PhonePayload, request: Request, user: CurrentUser, db: DbSession) -> PhoneResponse:
    """Задаёт или очищает телефон владельца. По нему клиника находит питомца и шлёт запрос.

    Номер пока не подтверждается по SMS (провайдера нет): это заведомое ограничение этапа.
    """
    if payload.phone is not None:
        taken = db.scalar(select(User.id).where(User.phone == payload.phone, User.id != user.id))
        if taken is not None:
            raise _error(status.HTTP_409_CONFLICT, "phone_taken", "Этот номер уже привязан к другому аккаунту")
    user.phone = payload.phone
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _error(status.HTTP_409_CONFLICT, "phone_taken", "Этот номер уже привязан к другому аккаунту") from exc
    # Сам номер в аудит не пишем: достаточно факта изменения.
    record_audit(
        db,
        action="profile.phone.updated",
        actor_user_id=user.id,
        entity="user",
        entity_id=user.id,
        request=request,
        details={"cleared": payload.phone is None},
    )
    return PhoneResponse(phone=user.phone)


# --- Код доступа (путь 1) -----------------------------------------------------------------


@router.post(
    "/pets/{pet_id}/access-codes", response_model=AccessCodeCreated, status_code=status.HTTP_201_CREATED
)
def create_access_code(
    pet_id: int, payload: AccessCodeCreate, request: Request, user: CurrentUser, db: DbSession
) -> AccessCodeCreated:
    """Создаёт одноразовый код на 15 минут. Прежний неиспользованный код питомца аннулируется."""
    pet = get_owned_pet(pet_id, user, db)
    now = datetime.now(UTC)

    db.execute(
        update(AccessCode)
        .where(AccessCode.pet_id == pet.id, AccessCode.used_at.is_(None), AccessCode.revoked_at.is_(None))
        .values(revoked_at=now)
    )

    # Хэш уникален за всё время: при (крайне редкой) коллизии просто берём другой код.
    for _ in range(5):
        code = generate_code()
        code_hash = hash_code(code)
        if db.scalar(select(AccessCode.id).where(AccessCode.code_hash == code_hash)) is None:
            break
    else:  # pragma: no cover - вероятность порядка 10^-30
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "code_generation_failed", "Повторите попытку")

    stored = AccessCode(
        pet_id=pet.id,
        created_by_id=user.id,
        code_hash=code_hash,
        scopes=ordered_scopes(payload.scopes),
        ttl_days=payload.ttl_days,
        expires_at=now + timedelta(minutes=CODE_TTL_MINUTES),
    )
    db.add(stored)
    db.commit()
    db.refresh(stored)
    record_audit(
        db,
        action="access_code.created",
        actor_user_id=user.id,
        entity="access_code",
        entity_id=stored.id,
        request=request,
        details={"pet_id": pet.id, "scopes": stored.scopes, "ttl_days": stored.ttl_days},
    )
    return AccessCodeCreated(
        id=stored.id,
        pet_id=stored.pet_id,
        scopes=stored.scopes,
        ttl_days=stored.ttl_days,
        expires_at=stored.expires_at,
        used_at=stored.used_at,
        revoked_at=stored.revoked_at,
        created_at=stored.created_at,
        code=format_code(code),
    )


@router.post("/access-codes/{code_id}/revoke", response_model=AccessCodeResponse)
def revoke_access_code(code_id: int, request: Request, user: CurrentUser, db: DbSession) -> AccessCode:
    """Аннулирует неиспользованный код, если он попал не в те руки."""
    stored = db.scalar(
        select(AccessCode)
        .join(Pet, Pet.id == AccessCode.pet_id)
        .where(AccessCode.id == code_id, Pet.owner_id == user.id)
    )
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access code not found")
    if stored.used_at is None and stored.revoked_at is None:
        stored.revoked_at = datetime.now(UTC)
        db.commit()
        db.refresh(stored)
        record_audit(
            db,
            action="access_code.revoked",
            actor_user_id=user.id,
            entity="access_code",
            entity_id=stored.id,
            request=request,
            details={"pet_id": stored.pet_id},
        )
    return stored


# --- Входящие запросы клиник (путь 2) ---------------------------------------------------------


def _owner_view(access_request: AccessRequest, pet: Pet, clinic: Clinic, now: datetime) -> OwnerAccessRequest:
    return OwnerAccessRequest(
        id=access_request.id,
        status=access_request.effective_status(now),
        clinic=ClinicBrief(id=clinic.id, name=clinic.name, address=clinic.address, phone=clinic.phone),
        pet=PetBrief(id=pet.id, name=pet.name, species=pet.species, photo_url=pet.photo_url),
        scopes=access_request.scopes,
        ttl_days=access_request.ttl_days,
        message=access_request.message,
        created_at=access_request.created_at,
        expires_at=access_request.expires_at,
        decided_at=access_request.decided_at,
        grant_id=access_request.grant_id,
    )


def _owned_request(db: Session, user: User, request_id: int) -> tuple[AccessRequest, Pet, Clinic]:
    row = db.execute(
        select(AccessRequest, Pet, Clinic)
        .join(Pet, Pet.id == AccessRequest.pet_id)
        .join(Clinic, Clinic.id == AccessRequest.clinic_id)
        .where(AccessRequest.id == request_id, Pet.owner_id == user.id)
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access request not found")
    return row[0], row[1], row[2]


def _require_pending(access_request: AccessRequest, now: datetime) -> None:
    current = access_request.effective_status(now)
    if current != REQUEST_PENDING:
        raise _error(
            status.HTTP_409_CONFLICT,
            "invalid_status",
            "Запрос уже обработан или истёк",
            current=current,
        )


@router.get("/access-requests", response_model=list[OwnerAccessRequest])
def list_access_requests(
    user: CurrentUser,
    pagination: PaginationParams,
    response: Response,
    db: DbSession,
    status_filter: Annotated[RequestStatusFilter | None, Query(alias="status", description="Статус запроса")] = None,
):
    """Запросы клиник к питомцам текущего владельца. Ожидающие запросы неактивных клиник скрыты."""
    now = datetime.now(UTC)
    conditions = [
        Pet.owner_id == user.id,
        or_(AccessRequest.status != REQUEST_PENDING, Clinic.status == CLINIC_APPROVED),
    ]
    if status_filter:
        conditions.append(request_status_condition(status_filter, now))

    base = (
        select(AccessRequest, Pet, Clinic)
        .join(Pet, Pet.id == AccessRequest.pet_id)
        .join(Clinic, Clinic.id == AccessRequest.clinic_id)
        .where(*conditions)
    )
    total = (
        db.scalar(
            select(func.count())
            .select_from(AccessRequest)
            .join(Pet, Pet.id == AccessRequest.pet_id)
            .join(Clinic, Clinic.id == AccessRequest.clinic_id)
            .where(*conditions)
        )
        or 0
    )
    rows = db.execute(base.order_by(AccessRequest.id.desc()).limit(pagination.limit).offset(pagination.offset)).all()
    pagination_headers(response, total=total, pagination=pagination)
    return [_owner_view(item, pet, clinic, now) for item, pet, clinic in rows]


@router.post("/access-requests/{request_id}/approve", response_model=OwnerAccessRequest)
def approve_access_request(
    request_id: int, payload: AccessRequestApprove, request: Request, user: CurrentUser, db: DbSession
) -> OwnerAccessRequest:
    """Открывает клинике доступ. Владелец может сузить разделы и срок, расширить нельзя."""
    now = datetime.now(UTC)
    access_request, pet, clinic = _owned_request(db, user, request_id)
    _require_pending(access_request, now)
    if clinic.status != CLINIC_APPROVED:
        raise _error(status.HTTP_409_CONFLICT, "clinic_unavailable", "Клиника сейчас недоступна")

    scopes = access_request.scopes
    if payload.scopes is not None:
        extra = set(payload.scopes) - set(access_request.scopes)
        if extra:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "scopes_not_requested",
                "Нельзя открыть больше, чем запросила клиника",
                extra=sorted(extra),
            )
        scopes = ordered_scopes(payload.scopes)

    ttl_days = access_request.ttl_days
    if payload.ttl_days is not None:
        if payload.ttl_days > access_request.ttl_days:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "ttl_too_long",
                "Нельзя дать доступ на больший срок, чем запросила клиника",
                requested=access_request.ttl_days,
            )
        ttl_days = payload.ttl_days

    grant = grant_clinic_access(db, clinic=clinic, pet_id=pet.id, scopes=scopes, ttl_days=ttl_days, now=now)
    access_request.status = REQUEST_APPROVED
    access_request.decided_at = now
    access_request.grant_id = grant.id
    db.commit()
    db.refresh(access_request)
    record_audit(
        db,
        action="access_request.approved",
        actor_user_id=user.id,
        entity="access_request",
        entity_id=access_request.id,
        request=request,
        details={"clinic_id": clinic.id, "pet_id": pet.id, "grant_id": grant.id, "scopes": scopes, "ttl_days": ttl_days},
    )
    return _owner_view(access_request, pet, clinic, now)


@router.post("/access-requests/{request_id}/deny", response_model=OwnerAccessRequest)
def deny_access_request(request_id: int, request: Request, user: CurrentUser, db: DbSession) -> OwnerAccessRequest:
    now = datetime.now(UTC)
    access_request, pet, clinic = _owned_request(db, user, request_id)
    _require_pending(access_request, now)
    access_request.status = REQUEST_DENIED
    access_request.decided_at = now
    db.commit()
    db.refresh(access_request)
    record_audit(
        db,
        action="access_request.denied",
        actor_user_id=user.id,
        entity="access_request",
        entity_id=access_request.id,
        request=request,
        details={"clinic_id": clinic.id, "pet_id": pet.id},
    )
    return _owner_view(access_request, pet, clinic, now)
