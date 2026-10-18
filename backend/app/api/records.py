"""Smart-ID: медзаписи питомца. Доступ только владельцу, всё пишется в историю."""

import json

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, get_owned_pet
from app.api.pagination import PaginationParams, pagination_headers
from app.models import AUTHOR_OWNER, SOURCE_MANUAL, MedicalRecord, Pet, RecordRevision
from app.schemas.medical import (
    RecordCreate,
    RecordResponse,
    RecordRevisionResponse,
    RecordUpdate,
)
from app.services.audit import record_audit

router = APIRouter(tags=["records"])


def _owned_record(record_id: int, user: CurrentUser, db: DbSession) -> MedicalRecord:
    """Запись доступна, только если её питомец принадлежит текущему пользователю."""
    record = db.scalar(
        select(MedicalRecord)
        .join(Pet, Pet.id == MedicalRecord.pet_id)
        .where(MedicalRecord.id == record_id, Pet.owner_id == user.id)
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
    return record


def _snapshot(record: MedicalRecord) -> str:
    """Снимок состояния для истории: хранится зашифрованным (это медданные)."""
    return json.dumps(
        {
            "kind": record.kind,
            "title": record.title,
            "occurred_at": record.occurred_at.isoformat(),
            "clinic_name": record.clinic_name,
            "description": record.description,
            "diagnosis": record.diagnosis,
        },
        ensure_ascii=False,
    )


@router.get("/pets/{pet_id}/records", response_model=list[RecordResponse])
def list_records(
    pet_id: int,
    user: CurrentUser,
    pagination: PaginationParams,
    response: Response,
    db: DbSession,
):
    get_owned_pet(pet_id, user, db)
    total = db.scalar(
        select(func.count()).select_from(MedicalRecord).where(MedicalRecord.pet_id == pet_id)
    ) or 0
    rows = db.scalars(
        select(MedicalRecord)
        .where(MedicalRecord.pet_id == pet_id)
        .order_by(MedicalRecord.occurred_at.desc(), MedicalRecord.id.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    ).all()
    pagination_headers(response, total=total, pagination=pagination)
    return list(rows)


@router.post("/pets/{pet_id}/records", response_model=RecordResponse, status_code=status.HTTP_201_CREATED)
def create_record(pet_id: int, payload: RecordCreate, request: Request, user: CurrentUser, db: DbSession):
    get_owned_pet(pet_id, user, db)

    record = MedicalRecord(
        pet_id=pet_id,
        author_type=AUTHOR_OWNER,
        author_user_id=user.id,
        source=SOURCE_MANUAL,
        **payload.model_dump(),
    )
    db.add(record)
    db.flush()
    db.add(
        RecordRevision(
            record_id=record.id,
            changed_by_id=user.id,
            action="created",
            snapshot=_snapshot(record),
        )
    )
    db.commit()
    db.refresh(record)
    record_audit(
        db,
        action="record.created",
        actor_user_id=user.id,
        entity="medical_record",
        entity_id=record.id,
        request=request,
        details={"pet_id": pet_id, "kind": record.kind},
    )
    return record


@router.get("/records/{record_id}", response_model=RecordResponse)
def get_record(record_id: int, user: CurrentUser, db: DbSession):
    return _owned_record(record_id, user, db)


@router.patch("/records/{record_id}", response_model=RecordResponse)
def update_record(
    record_id: int, payload: RecordUpdate, request: Request, user: CurrentUser, db: DbSession
):
    record = _owned_record(record_id, user, db)
    changes = payload.model_dump(exclude_unset=True)

    if changes:
        # Снимок того, что было, кладём в историю до применения изменений.
        db.add(
            RecordRevision(
                record_id=record.id,
                changed_by_id=user.id,
                action="updated",
                snapshot=_snapshot(record),
            )
        )
        for key, value in changes.items():
            setattr(record, key, value)
        db.commit()
        db.refresh(record)
        record_audit(
            db,
            action="record.updated",
            actor_user_id=user.id,
            entity="medical_record",
            entity_id=record.id,
            request=request,
            details={"fields": sorted(changes)},
        )
    return record


@router.delete("/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_record(record_id: int, request: Request, user: CurrentUser, db: DbSession):
    record = _owned_record(record_id, user, db)
    record_id_value = record.id
    pet_id = record.pet_id
    db.delete(record)
    db.commit()
    record_audit(
        db,
        action="record.deleted",
        actor_user_id=user.id,
        entity="medical_record",
        entity_id=record_id_value,
        request=request,
        details={"pet_id": pet_id},
    )


@router.get("/records/{record_id}/revisions", response_model=list[RecordRevisionResponse])
def list_revisions(record_id: int, user: CurrentUser, db: DbSession, limit: int = 50):
    """История изменений записи (без раскрытия прежних текстов в списке)."""
    _owned_record(record_id, user, db)
    rows = db.scalars(
        select(RecordRevision)
        .where(RecordRevision.record_id == record_id)
        .order_by(RecordRevision.id.desc())
        .limit(max(1, min(limit, 200)))
    ).all()
    return list(rows)


@router.get("/records/{record_id}/revisions/{revision_id}", response_model=dict)
def get_revision(record_id: int, revision_id: int, user: CurrentUser, db: DbSession) -> dict:
    """Снимок прежнего состояния: врачу и владельцу полезно видеть, что менялось."""
    _owned_record(record_id, user, db)
    revision = db.get(RecordRevision, revision_id)
    if revision is None or revision.record_id != record_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revision not found")
    return {
        "id": revision.id,
        "action": revision.action,
        "created_at": revision.created_at.isoformat(),
        "before": json.loads(revision.snapshot),
    }
