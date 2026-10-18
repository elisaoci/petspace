"""Доступ к медкарте по ссылке: выдача, список, отзыв и публичное чтение.

Владелец выдаёт доступ с названием («Клиника «Айболит», врач Иванов»), набором разделов
и сроком. Токен показывается один раз, в базе лежит только его хэш. Отзыв действует сразу.
"""

from datetime import UTC, date, datetime, timedelta
from secrets import token_urlsafe

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, get_owned_pet
from app.models import (
    RECORD_VACCINATION,
    SCOPE_PROFILE,
    SCOPE_RECORDS,
    SCOPE_VACCINATIONS,
    AccessGrant,
    MedicalRecord,
    Pet,
)
from app.schemas.medical import (
    AccessGrantCreate,
    AccessGrantCreated,
    AccessGrantResponse,
    PublicAccessGrant,
    PublicAccessResponse,
    PublicPetProfile,
    PublicRecord,
)
from app.services.audit import ACTOR_ANONYMOUS, record_audit
from app.services.security import hash_token

router = APIRouter(tags=["access"])

ACCESS_NOT_FOUND = "Ссылка недействительна, истекла или отозвана"


def _owned_grant(grant_id: int, user: CurrentUser, db: DbSession) -> AccessGrant:
    grant = db.scalar(
        select(AccessGrant)
        .join(Pet, Pet.id == AccessGrant.pet_id)
        .where(AccessGrant.id == grant_id, Pet.owner_id == user.id)
    )
    if grant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access grant not found")
    return grant


@router.get("/pets/{pet_id}/access-grants", response_model=list[AccessGrantResponse])
def list_grants(pet_id: int, user: CurrentUser, db: DbSession):
    get_owned_pet(pet_id, user, db)
    return list(
        db.scalars(
            select(AccessGrant)
            .where(AccessGrant.pet_id == pet_id)
            .order_by(AccessGrant.id.desc())
        ).all()
    )


@router.post(
    "/pets/{pet_id}/access-grants",
    response_model=AccessGrantCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_grant(
    pet_id: int, payload: AccessGrantCreate, request: Request, user: CurrentUser, db: DbSession
):
    pet = get_owned_pet(pet_id, user, db)
    now = datetime.now(UTC)
    token = token_urlsafe(32)

    grant = AccessGrant(
        pet_id=pet.id,
        label=payload.label,
        token_hash=hash_token(token),
        scopes=list(dict.fromkeys(payload.scopes)),
        expires_at=now + timedelta(days=payload.ttl_days),
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)

    record_audit(
        db,
        action="access.granted",
        actor_user_id=user.id,
        entity="access_grant",
        entity_id=grant.id,
        request=request,
        details={"pet_id": pet.id, "scopes": grant.scopes, "ttl_days": payload.ttl_days},
    )

    return AccessGrantCreated(
        id=grant.id,
        pet_id=grant.pet_id,
        label=grant.label,
        scopes=grant.scopes,
        expires_at=grant.expires_at,
        revoked_at=grant.revoked_at,
        last_used_at=grant.last_used_at,
        created_at=grant.created_at,
        token=token,
        url=f"/medical/access/{token}",
    )


@router.post("/access-grants/{grant_id}/revoke", response_model=AccessGrantResponse)
def revoke_grant(grant_id: int, request: Request, user: CurrentUser, db: DbSession):
    grant = _owned_grant(grant_id, user, db)
    if grant.revoked_at is None:
        grant.revoked_at = datetime.now(UTC)
        db.commit()
        db.refresh(grant)
        record_audit(
            db,
            action="access.revoked",
            actor_user_id=user.id,
            entity="access_grant",
            entity_id=grant.id,
            request=request,
            details={"pet_id": grant.pet_id},
        )
    return grant


@router.get("/medical/access/{token}", response_model=PublicAccessResponse)
def read_by_token(token: str, request: Request, db: DbSession) -> PublicAccessResponse:
    """Публичное чтение медкарты по ссылке. Без авторизации, но с аудитом и сроками."""
    grant = db.scalar(select(AccessGrant).where(AccessGrant.token_hash == hash_token(token)))
    now = datetime.now(UTC)

    if grant is None or not grant.is_active(now):
        record_audit(
            db,
            action="medical_access.read",
            actor_type=ACTOR_ANONYMOUS,
            entity="access_grant",
            request=request,
            details={"result": "denied"},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "access_not_found", "message": ACCESS_NOT_FOUND},
        )

    pet = db.get(Pet, grant.pet_id)
    if pet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "access_not_found", "message": ACCESS_NOT_FOUND},
        )

    grant.last_used_at = now
    db.commit()
    record_audit(
        db,
        action="medical_access.read",
        actor_type=ACTOR_ANONYMOUS,
        entity="pet",
        entity_id=pet.id,
        request=request,
        details={"grant_id": grant.id, "scopes": grant.scopes},
    )

    response = PublicAccessResponse(
        grant=PublicAccessGrant(label=grant.label, scopes=grant.scopes, expires_at=grant.expires_at)
    )

    if grant.has_scope(SCOPE_PROFILE):
        response.pet = PublicPetProfile(
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

    records = list(
        db.scalars(
            select(MedicalRecord)
            .where(MedicalRecord.pet_id == pet.id)
            .order_by(MedicalRecord.occurred_at.desc(), MedicalRecord.id.desc())
        ).all()
    )

    if grant.has_scope(SCOPE_RECORDS):
        response.records = [_public_record(record) for record in records]

    if grant.has_scope(SCOPE_VACCINATIONS):
        response.vaccinations = [
            _public_record(record) for record in records if record.kind == RECORD_VACCINATION
        ]

    return response


def _public_record(record: MedicalRecord) -> PublicRecord:
    return PublicRecord(
        id=record.id,
        kind=record.kind,
        title=record.title,
        occurred_at=record.occurred_at,
        clinic_name=record.clinic_name,
        author_type=record.author_type,
        description=record.description,
        diagnosis=record.diagnosis,
    )


def _age_years(birth_date: date | None) -> int | None:
    if birth_date is None:
        return None
    today = date.today()
    return (
        today.year
        - birth_date.year
        - ((today.month, today.day) < (birth_date.month, birth_date.day))
    )


