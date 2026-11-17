"""Доступ клиники к пациенту: ввод кода, запросы по телефону, список пациентов и карта.

Как клиника получает доступ:

1. **Код владельца.** `POST /clinics/me/access-codes/redeem`: владелец показал код или QR,
   сотрудник ввёл его, доступ открыт сразу.
2. **Запрос по телефону.** `POST /clinics/me/access-requests`: имя питомца и телефон владельца.
   Владелец подтверждает в приложении. Ответ API одинаков, нашёлся питомец или нет:
   перебором телефонов узнать, кто зарегистрирован, нельзя.

Чтение карты (`GET /clinics/me/patients/{pet_id}`) возможно только по действующему доступу
этой клиники. Любой чужой или отозванный доступ отвечает 404. Каждое чтение пишется в аудит.
Регистратор видит только профиль питомца, врач и администратор — все выданные разделы.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.access import _age_years, _public_record  # сборка ответа та же, что у публичной ссылки
from app.api.clinic_deps import ApprovedClinicMember, ClinicContext
from app.api.deps import CurrentUser, DbSession
from app.api.pagination import PaginationParams, pagination_headers
from app.models import (
    CLINIC_APPROVED,
    RECORD_VACCINATION,
    REQUEST_APPROVED,
    REQUEST_CANCELLED,
    REQUEST_PENDING,
    SCOPE_PROFILE,
    SCOPE_RECORDS,
    SCOPE_VACCINATIONS,
    STATUS_ACTIVE,
    AccessCode,
    AccessGrant,
    AccessRequest,
    Clinic,
    ClinicStaff,
    MedicalRecord,
    Pet,
    User,
)
from app.schemas.medical import PublicAccessGrant, PublicAccessResponse, PublicPetProfile
from app.schemas.patient_access import (
    AccessRequestCreate,
    ClinicAccessRequest,
    DirectoryClinic,
    PatientAccessResponse,
    PatientBrief,
    PatientListItem,
    RedeemPayload,
    RequestStatusFilter,
)
from app.services.audit import record_audit
from app.services.patient_access import (
    MAX_FAILED_CODE_ATTEMPTS_PER_HOUR,
    MAX_REQUESTS_PER_DAY,
    REQUEST_TTL_HOURS,
    failed_code_attempts_last_hour,
    grant_clinic_access,
    hash_code,
    mask_phone,
    normalize_code,
    ordered_scopes,
    request_status_condition,
    requests_last_day,
    visible_scopes,
)

router = APIRouter(prefix="/clinics", tags=["patient-access"])

CODE_INVALID = "Код недействителен, истёк или уже использован"


# --- Вспомогательное ----------------------------------------------------------------


def _error(http_status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"error": code, "message": message})


def _patient_brief(pet: Pet) -> PatientBrief:
    return PatientBrief(id=pet.id, name=pet.name, species=pet.species, breed=pet.breed, photo_url=pet.photo_url)


def _find_pet(db: Session, phone: str, pet_name: str) -> Pet | None:
    """Питомец владельца с этим телефоном и этим именем (без учёта регистра и пробелов по краям)."""
    owner = db.scalar(select(User).where(User.phone == phone, User.status == STATUS_ACTIVE))
    if owner is None:
        return None
    wanted = pet_name.strip().casefold()
    pets = db.scalars(select(Pet).where(Pet.owner_id == owner.id).order_by(Pet.id)).all()
    return next((pet for pet in pets if pet.name.strip().casefold() == wanted), None)


def _active_grant(db: Session, clinic_id: int, pet_id: int, now: datetime) -> AccessGrant | None:
    return db.scalar(
        select(AccessGrant)
        .where(
            AccessGrant.clinic_id == clinic_id,
            AccessGrant.pet_id == pet_id,
            AccessGrant.revoked_at.is_(None),
            AccessGrant.expires_at > now,
        )
        .order_by(AccessGrant.id.desc())
    )


def _request_response(
    db: Session, access_request: AccessRequest, now: datetime, staff_names: dict[int, str]
) -> ClinicAccessRequest:
    effective = access_request.effective_status(now)
    patient = None
    # Пациент раскрывается только после одобрения владельцем.
    if effective == REQUEST_APPROVED and access_request.pet_id is not None:
        pet = db.get(Pet, access_request.pet_id)
        patient = _patient_brief(pet) if pet is not None else None
    requested_by = staff_names.get(access_request.requested_by_id) if access_request.requested_by_id else None
    return ClinicAccessRequest(
        id=access_request.id,
        status=effective,
        pet_name=access_request.pet_name_query,
        owner_phone_masked=mask_phone(access_request.owner_phone_query),
        scopes=access_request.scopes,
        ttl_days=access_request.ttl_days,
        message=access_request.message,
        requested_by=requested_by,
        created_at=access_request.created_at,
        expires_at=access_request.expires_at,
        decided_at=access_request.decided_at,
        patient=patient,
        grant_id=access_request.grant_id if patient is not None else None,
    )


def _staff_names(db: Session, clinic_id: int) -> dict[int, str]:
    rows = db.execute(select(ClinicStaff.user_id, ClinicStaff.full_name).where(ClinicStaff.clinic_id == clinic_id)).all()
    return {row.user_id: row.full_name for row in rows}


# --- Справочник клиник (для владельцев) -------------------------------------------------


@router.get("/directory", response_model=list[DirectoryClinic])
def clinic_directory(
    user: CurrentUser,
    pagination: PaginationParams,
    response: Response,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=100, description="Поиск по названию")] = None,
):
    """Подтверждённые клиники для выбора в приложении владельца. Только для вошедших."""
    conditions = [Clinic.status == CLINIC_APPROVED]
    if q and q.strip():
        term = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(Clinic.name.ilike(f"%{term}%", escape="\\"))
    total = db.scalar(select(func.count()).select_from(Clinic).where(*conditions)) or 0
    rows = db.scalars(
        select(Clinic).where(*conditions).order_by(Clinic.name, Clinic.id).limit(pagination.limit).offset(pagination.offset)
    ).all()
    pagination_headers(response, total=total, pagination=pagination)
    return list(rows)


# --- Путь 1: код владельца --------------------------------------------------------------


@router.post("/me/access-codes/redeem", response_model=PatientAccessResponse)
def redeem_code(
    payload: RedeemPayload, request: Request, ctx: ApprovedClinicMember, db: DbSession
) -> PatientAccessResponse:
    """Ввод кода или QR от владельца: доступ к питомцу открывается сразу, код сгорает."""
    now = datetime.now(UTC)
    if failed_code_attempts_last_hour(db, ctx.clinic.id, now) >= MAX_FAILED_CODE_ATTEMPTS_PER_HOUR:
        raise _error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too_many_attempts",
            "Слишком много неверных кодов, попробуйте через час",
        )

    code = normalize_code(payload.code)
    stored = db.scalar(select(AccessCode).where(AccessCode.code_hash == hash_code(code))) if code else None
    claimed = False
    if stored is not None and stored.is_usable(now):
        # Атомарно занимаем код: два одновременных ввода не откроют доступ дважды.
        result = db.execute(
            update(AccessCode)
            .where(AccessCode.id == stored.id, AccessCode.used_at.is_(None), AccessCode.revoked_at.is_(None))
            .values(used_at=now, used_by_clinic_id=ctx.clinic.id)
        )
        claimed = result.rowcount == 1

    if not claimed or stored is None:
        db.rollback()
        record_audit(
            db,
            action="access_code.redeem_failed",
            actor_user_id=ctx.user.id,
            entity="access_code",
            request=request,
            details={"clinic_id": ctx.clinic.id},
        )
        # Причина не раскрывается: неверный, истёкший и использованный код выглядят одинаково.
        raise _error(status.HTTP_404_NOT_FOUND, "code_invalid", CODE_INVALID)

    pet = db.get(Pet, stored.pet_id)
    grant = grant_clinic_access(
        db, clinic=ctx.clinic, pet_id=stored.pet_id, scopes=stored.scopes, ttl_days=stored.ttl_days, now=now
    )
    db.commit()
    record_audit(
        db,
        action="access_code.redeemed",
        actor_user_id=ctx.user.id,
        entity="access_grant",
        entity_id=grant.id,
        request=request,
        details={"clinic_id": ctx.clinic.id, "pet_id": stored.pet_id, "code_id": stored.id},
    )
    return PatientAccessResponse(
        grant_id=grant.id,
        pet=_patient_brief(pet),
        scopes=visible_scopes(ctx.staff.role, grant.scopes),
        expires_at=grant.expires_at,
    )


# --- Путь 2: запрос по имени питомца и телефону владельца ------------------------------


@router.post("/me/access-requests", response_model=ClinicAccessRequest, status_code=status.HTTP_201_CREATED)
def create_access_request(
    payload: AccessRequestCreate, request: Request, ctx: ApprovedClinicMember, db: DbSession
) -> ClinicAccessRequest:
    """Запрос доступа. Владелец увидит его в приложении и сам решит, открывать ли карту.

    Запись создаётся и тогда, когда питомец не найден: ответ не отличается, поэтому
    клиника не может проверять, чей телефон зарегистрирован в PetSpace.
    """
    now = datetime.now(UTC)
    if requests_last_day(db, ctx.clinic.id, now) >= MAX_REQUESTS_PER_DAY:
        raise _error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too_many_requests",
            "Достигнут суточный лимит запросов доступа",
        )

    name_key = payload.pet_name.casefold()
    same_open = db.scalars(
        select(AccessRequest).where(
            AccessRequest.clinic_id == ctx.clinic.id,
            AccessRequest.owner_phone_query == payload.owner_phone,
            request_status_condition(REQUEST_PENDING, now),
        )
    ).all()
    if any(item.pet_name_query.casefold() == name_key for item in same_open):
        raise _error(status.HTTP_409_CONFLICT, "request_pending", "Такой запрос уже отправлен и ждёт ответа владельца")

    pet = _find_pet(db, payload.owner_phone, payload.pet_name)
    access_request = AccessRequest(
        clinic_id=ctx.clinic.id,
        requested_by_id=ctx.user.id,
        pet_id=pet.id if pet else None,
        pet_name_query=payload.pet_name,
        owner_phone_query=payload.owner_phone,
        scopes=ordered_scopes(payload.scopes),
        ttl_days=payload.ttl_days,
        message=payload.message,
        status=REQUEST_PENDING,
        expires_at=now + timedelta(hours=REQUEST_TTL_HOURS),
    )
    db.add(access_request)
    db.commit()
    db.refresh(access_request)
    record_audit(
        db,
        action="access_request.created",
        actor_user_id=ctx.user.id,
        entity="access_request",
        entity_id=access_request.id,
        request=request,
        # Совпадение пишем в журнал, но не в ответ клинике.
        details={"clinic_id": ctx.clinic.id, "matched": pet is not None},
    )
    return _request_response(db, access_request, now, {ctx.user.id: ctx.staff.full_name})


@router.get("/me/access-requests", response_model=list[ClinicAccessRequest])
def list_access_requests(
    ctx: ApprovedClinicMember,
    pagination: PaginationParams,
    response: Response,
    db: DbSession,
    status_filter: Annotated[RequestStatusFilter | None, Query(alias="status", description="Статус запроса")] = None,
):
    now = datetime.now(UTC)
    conditions = [AccessRequest.clinic_id == ctx.clinic.id]
    if status_filter:
        conditions.append(request_status_condition(status_filter, now))
    total = db.scalar(select(func.count()).select_from(AccessRequest).where(*conditions)) or 0
    rows = db.scalars(
        select(AccessRequest)
        .where(*conditions)
        .order_by(AccessRequest.id.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    ).all()
    names = _staff_names(db, ctx.clinic.id)
    pagination_headers(response, total=total, pagination=pagination)
    return [_request_response(db, item, now, names) for item in rows]


@router.post("/me/access-requests/{request_id}/cancel", response_model=ClinicAccessRequest)
def cancel_access_request(
    request_id: int, request: Request, ctx: ApprovedClinicMember, db: DbSession
) -> ClinicAccessRequest:
    now = datetime.now(UTC)
    access_request = db.scalar(
        select(AccessRequest).where(AccessRequest.id == request_id, AccessRequest.clinic_id == ctx.clinic.id)
    )
    if access_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access request not found")
    current = access_request.effective_status(now)
    if current != REQUEST_PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "invalid_status", "message": "Отменить можно только ожидающий запрос", "current": current},
        )
    access_request.status = REQUEST_CANCELLED
    access_request.decided_at = now
    db.commit()
    db.refresh(access_request)
    record_audit(
        db,
        action="access_request.cancelled",
        actor_user_id=ctx.user.id,
        entity="access_request",
        entity_id=access_request.id,
        request=request,
        details={"clinic_id": ctx.clinic.id},
    )
    return _request_response(db, access_request, now, _staff_names(db, ctx.clinic.id))


# --- Пациенты клиники ---------------------------------------------------------------------


@router.get("/me/patients", response_model=list[PatientListItem])
def list_patients(ctx: ApprovedClinicMember, pagination: PaginationParams, response: Response, db: DbSession):
    """Питомцы, к которым у клиники сейчас есть действующий доступ."""
    now = datetime.now(UTC)
    conditions = [
        AccessGrant.clinic_id == ctx.clinic.id,
        AccessGrant.revoked_at.is_(None),
        AccessGrant.expires_at > now,
    ]
    total = db.scalar(select(func.count()).select_from(AccessGrant).where(*conditions)) or 0
    rows = db.execute(
        select(AccessGrant, Pet)
        .join(Pet, Pet.id == AccessGrant.pet_id)
        .where(*conditions)
        .order_by(AccessGrant.id.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    ).all()
    pagination_headers(response, total=total, pagination=pagination)
    return [
        PatientListItem(
            pet=_patient_brief(pet),
            grant_id=grant.id,
            scopes=visible_scopes(ctx.staff.role, grant.scopes),
            expires_at=grant.expires_at,
            last_used_at=grant.last_used_at,
        )
        for grant, pet in rows
    ]


@router.get("/me/patients/{pet_id}", response_model=PublicAccessResponse)
def get_patient_card(pet_id: int, request: Request, ctx: ApprovedClinicMember, db: DbSession) -> PublicAccessResponse:
    """Карта пациента в пределах выданных разделов и прав роли. Каждое чтение попадает в аудит."""
    now = datetime.now(UTC)
    grant = _active_grant(db, ctx.clinic.id, pet_id, now)
    pet = db.get(Pet, pet_id) if grant is not None else None
    if grant is None or pet is None:
        # Нет доступа, он истёк или отозван, питомца нет, он чужой — ответ один и тот же.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    scopes = visible_scopes(ctx.staff.role, grant.scopes)
    card = _build_card(db, ctx, pet, grant, scopes)

    grant.last_used_at = now
    db.commit()
    record_audit(
        db,
        action="patient.read",
        actor_user_id=ctx.user.id,
        entity="pet",
        entity_id=pet_id,
        request=request,
        details={"clinic_id": ctx.clinic.id, "grant_id": grant.id, "scopes": scopes},
    )
    return card


def _build_card(db: Session, ctx: ClinicContext, pet: Pet, grant: AccessGrant, scopes: list[str]) -> PublicAccessResponse:
    card = PublicAccessResponse(
        grant=PublicAccessGrant(label=ctx.clinic.name, scopes=scopes, expires_at=grant.expires_at)
    )
    if SCOPE_PROFILE in scopes:
        card.pet = PublicPetProfile(
            id=pet.id,
            name=pet.name,
            species=pet.species,
            breed=pet.breed,
            sex=pet.sex,
            birth_date=pet.birth_date,
            weight_kg=pet.weight_kg,
            height_cm=pet.height_cm,
            photo_url=pet.photo_url,
            allergies=pet.allergies,
            chronic_conditions=pet.chronic_conditions,
            age_years=_age_years(pet.birth_date),
        )

    if SCOPE_RECORDS in scopes or SCOPE_VACCINATIONS in scopes:
        records = list(
            db.scalars(
                select(MedicalRecord)
                .where(MedicalRecord.pet_id == pet.id)
                .order_by(MedicalRecord.occurred_at.desc(), MedicalRecord.id.desc())
            ).all()
        )
        if SCOPE_RECORDS in scopes:
            card.records = [_public_record(record) for record in records]
        if SCOPE_VACCINATIONS in scopes:
            card.vaccinations = [_public_record(record) for record in records if record.kind == RECORD_VACCINATION]
    return card
