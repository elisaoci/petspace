"""Кабинет врача: приём пациента, записи в медкарту, вложения.

Как проходит приём:

1. Врач открывает карту пациента (`GET /clinics/me/patients/{id}`: анамнез, аллергии, история)
   и начинает приём: `POST /clinics/me/patients/{pet_id}/encounters`.
2. Во время приёма добавляет записи: осмотр, анализы, назначения, прививки
   (`POST /clinics/me/encounters/{id}/records`) и прикрепляет файлы.
3. Завершает приём: `POST /clinics/me/encounters/{id}/finish`. Время приёма фиксируется.

Записи сразу видны владельцу в его медкарте (`author_type = clinic`, название клиники),
попадают в историю изменений и в журнал аудита.

Правила доступа:

- вести приём могут врач и администратор клиники, регистратор — нет;
- писать и читать медданные можно только пока у клиники есть действующий доступ к питомцу
  с нужным разделом (см. `app/services/encounters.py`); владелец отозвал доступ, и запись
  закрыта в ту же секунду;
- менять можно только записи, созданные своей клиникой; правки пишутся в историю версий;
- удалять записи клиника не может: исправление идёт правкой с сохранением прежней версии.
"""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, undefer

from app.api.clinic_deps import ClinicContext, require_clinic_roles
from app.api.deps import DbSession
from app.api.pagination import PaginationParams, pagination_headers
from app.api.patient_access import _active_grant, _patient_brief, _staff_names  # общие с чтением карты
from app.api.records import _snapshot  # тот же снимок для истории, что и у владельца
from app.models import (
    AUTHOR_CLINIC,
    ENCOUNTER_COMPLETED,
    ENCOUNTER_IN_PROGRESS,
    ROLE_CLINIC_ADMIN,
    ROLE_CLINIC_DOCTOR,
    SOURCE_MANUAL,
    AccessGrant,
    Encounter,
    MedicalRecord,
    Pet,
    RecordAttachment,
    RecordRevision,
)
from app.schemas.encounters import (
    AttachmentResponse,
    ClinicRecordCreate,
    ClinicRecordResponse,
    ClinicRecordUpdate,
    EncounterDetail,
    EncounterResponse,
)
from app.services.audit import record_audit
from app.services.clinics import (
    MAX_DOCUMENT_BYTES,
    DocumentError,
    content_disposition,
    detect_document_type,
    safe_filename,
)
from app.services.encounters import (
    MAX_ATTACHMENTS_PER_RECORD,
    MAX_FUTURE_SKEW,
    grant_allows_kind,
    scopes_for_kind,
)

router = APIRouter(prefix="/clinics/me", tags=["encounters"])

DoctorOrAdmin = Annotated[ClinicContext, Depends(require_clinic_roles(ROLE_CLINIC_DOCTOR, ROLE_CLINIC_ADMIN))]
EncounterStatusFilter = Literal["in_progress", "completed"]


# --- Вспомогательное ----------------------------------------------------------------


def _error(http_status: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"error": code, "message": message, **extra})


def _own_encounter(db: Session, ctx: ClinicContext, encounter_id: int) -> Encounter:
    encounter = db.scalar(
        select(Encounter).where(Encounter.id == encounter_id, Encounter.clinic_id == ctx.clinic.id)
    )
    if encounter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encounter not found")
    return encounter


def _require_grant(
    db: Session, ctx: ClinicContext, pet_id: int, now: datetime, kind: str | None = None
) -> AccessGrant:
    """Действующий доступ клиники к питомцу и, если указан вид записи, нужный раздел."""
    grant = _active_grant(db, ctx.clinic.id, pet_id, now)
    if grant is None:
        raise _error(
            status.HTTP_403_FORBIDDEN, "access_required", "Доступ к карте пациента истёк или отозван владельцем"
        )
    if kind is not None and not grant_allows_kind(grant.scopes, kind):
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "scope_required",
            "Владелец не открыл клинике этот раздел карты",
            kind=kind,
            required=list(scopes_for_kind(kind)),
        )
    return grant


def _as_aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _check_not_future(moment: datetime, now: datetime) -> None:
    if _as_aware(moment) > now + MAX_FUTURE_SKEW:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "occurred_in_future", "Время записи не может быть в будущем")


def _attachments_by_record(db: Session, record_ids: list[int]) -> dict[int, list[RecordAttachment]]:
    if not record_ids:
        return {}
    rows = db.scalars(
        select(RecordAttachment).where(RecordAttachment.record_id.in_(record_ids)).order_by(RecordAttachment.id)
    ).all()
    grouped: dict[int, list[RecordAttachment]] = {}
    for row in rows:
        grouped.setdefault(row.record_id, []).append(row)
    return grouped


def _record_response(
    record: MedicalRecord, names: dict[int, str], attachments: list[RecordAttachment]
) -> ClinicRecordResponse:
    return ClinicRecordResponse(
        id=record.id,
        pet_id=record.pet_id,
        encounter_id=record.encounter_id,
        kind=record.kind,
        title=record.title,
        occurred_at=record.occurred_at,
        description=record.description,
        diagnosis=record.diagnosis,
        clinic_name=record.clinic_name,
        author_type=record.author_type,
        author_name=names.get(record.author_user_id) if record.author_user_id else None,
        created_at=record.created_at,
        updated_at=record.updated_at,
        attachments=[AttachmentResponse.model_validate(item) for item in attachments],
    )


def _single_record_response(db: Session, ctx: ClinicContext, record: MedicalRecord) -> ClinicRecordResponse:
    names = _staff_names(db, ctx.clinic.id)
    return _record_response(record, names, _attachments_by_record(db, [record.id]).get(record.id, []))


def _encounter_responses(db: Session, ctx: ClinicContext, encounters: list[Encounter]) -> list[EncounterResponse]:
    if not encounters:
        return []
    ids = [item.id for item in encounters]
    pets = {
        pet.id: pet
        for pet in db.scalars(select(Pet).where(Pet.id.in_(list({item.pet_id for item in encounters})))).all()
    }
    counts = dict(
        db.execute(
            select(MedicalRecord.encounter_id, func.count())
            .where(MedicalRecord.encounter_id.in_(ids))
            .group_by(MedicalRecord.encounter_id)
        ).all()
    )
    names = _staff_names(db, ctx.clinic.id)
    return [
        EncounterResponse(
            id=item.id,
            pet=_patient_brief(pets[item.pet_id]),
            status=item.status,
            doctor_name=names.get(item.doctor_user_id) if item.doctor_user_id else None,
            started_at=item.started_at,
            finished_at=item.finished_at,
            duration_seconds=item.duration_seconds(),
            records_count=counts.get(item.id, 0),
        )
        for item in encounters
    ]


def _encounter_detail(
    db: Session, ctx: ClinicContext, encounter: Encounter, grant: AccessGrant
) -> EncounterDetail:
    base = _encounter_responses(db, ctx, [encounter])[0].model_dump()
    records = db.scalars(
        select(MedicalRecord)
        .where(MedicalRecord.encounter_id == encounter.id)
        .order_by(MedicalRecord.occurred_at, MedicalRecord.id)
    ).all()
    # Если владелец позже сузил доступ, разделы вне доступа не показываем и в чужом приёме.
    visible = [record for record in records if grant_allows_kind(grant.scopes, record.kind)]
    names = _staff_names(db, ctx.clinic.id)
    attachments = _attachments_by_record(db, [record.id for record in visible])
    base["records_count"] = len(visible)
    return EncounterDetail(
        **base, records=[_record_response(record, names, attachments.get(record.id, [])) for record in visible]
    )


# --- Приёмы -------------------------------------------------------------------------------


@router.post(
    "/patients/{pet_id}/encounters", response_model=EncounterDetail, status_code=status.HTTP_201_CREATED
)
def start_encounter(pet_id: int, request: Request, ctx: DoctorOrAdmin, db: DbSession) -> EncounterDetail:
    """Начинает приём. Нужен действующий доступ клиники к питомцу; на питомца — один открытый приём."""
    now = datetime.now(UTC)
    grant = _active_grant(db, ctx.clinic.id, pet_id, now)
    pet = db.get(Pet, pet_id) if grant is not None else None
    if grant is None or pet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    open_encounter = db.scalar(
        select(Encounter).where(
            Encounter.clinic_id == ctx.clinic.id,
            Encounter.pet_id == pet_id,
            Encounter.status == ENCOUNTER_IN_PROGRESS,
        )
    )
    if open_encounter is not None:
        raise _error(
            status.HTTP_409_CONFLICT,
            "encounter_in_progress",
            "По этому питомцу уже идёт приём",
            encounter_id=open_encounter.id,
        )

    encounter = Encounter(
        clinic_id=ctx.clinic.id,
        pet_id=pet_id,
        doctor_user_id=ctx.user.id,
        status=ENCOUNTER_IN_PROGRESS,
        started_at=now,
    )
    try:
        db.add(encounter)
        db.commit()
    except IntegrityError as exc:
        # Два одновременных старта: частичный уникальный индекс пропустил только один.
        db.rollback()
        raise _error(status.HTTP_409_CONFLICT, "encounter_in_progress", "По этому питомцу уже идёт приём") from exc
    db.refresh(encounter)
    detail = _encounter_detail(db, ctx, encounter, grant)
    record_audit(
        db,
        action="encounter.started",
        actor_user_id=ctx.user.id,
        entity="encounter",
        entity_id=encounter.id,
        request=request,
        details={"clinic_id": ctx.clinic.id, "pet_id": pet_id},
    )
    return detail


@router.get("/encounters", response_model=list[EncounterResponse])
def list_encounters(
    ctx: DoctorOrAdmin,
    pagination: PaginationParams,
    response: Response,
    db: DbSession,
    status_filter: Annotated[EncounterStatusFilter | None, Query(alias="status", description="Статус приёма")] = None,
    pet_id: Annotated[int | None, Query(ge=1, description="Только приёмы этого питомца")] = None,
    mine: Annotated[bool, Query(description="Только приёмы, начатые мной")] = False,
):
    """Приёмы клиники, свежие сверху. Без медицинского содержимого, поэтому доступ клиники не нужен."""
    conditions = [Encounter.clinic_id == ctx.clinic.id]
    if status_filter:
        conditions.append(Encounter.status == status_filter)
    if pet_id:
        conditions.append(Encounter.pet_id == pet_id)
    if mine:
        conditions.append(Encounter.doctor_user_id == ctx.user.id)
    total = db.scalar(select(func.count()).select_from(Encounter).where(*conditions)) or 0
    rows = db.scalars(
        select(Encounter)
        .where(*conditions)
        .order_by(Encounter.started_at.desc(), Encounter.id.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    ).all()
    pagination_headers(response, total=total, pagination=pagination)
    return _encounter_responses(db, ctx, list(rows))


@router.get("/encounters/{encounter_id}", response_model=EncounterDetail)
def get_encounter(encounter_id: int, ctx: DoctorOrAdmin, db: DbSession) -> EncounterDetail:
    """Приём вместе с записями. Содержимое медицинское, поэтому нужен действующий доступ."""
    encounter = _own_encounter(db, ctx, encounter_id)
    grant = _require_grant(db, ctx, encounter.pet_id, datetime.now(UTC))
    return _encounter_detail(db, ctx, encounter, grant)


@router.post("/encounters/{encounter_id}/finish", response_model=EncounterResponse)
def finish_encounter(encounter_id: int, request: Request, ctx: DoctorOrAdmin, db: DbSession) -> EncounterResponse:
    """Завершает приём и фиксирует время. Врач завершает свой приём, администратор — любой."""
    encounter = _own_encounter(db, ctx, encounter_id)
    if encounter.status != ENCOUNTER_IN_PROGRESS:
        raise _error(
            status.HTTP_409_CONFLICT, "invalid_status", "Приём уже завершён", current=encounter.status
        )
    if ctx.staff.role != ROLE_CLINIC_ADMIN and encounter.doctor_user_id != ctx.user.id:
        raise _error(status.HTTP_403_FORBIDDEN, "not_your_encounter", "Завершить приём может его врач или администратор")

    encounter.status = ENCOUNTER_COMPLETED
    encounter.finished_at = datetime.now(UTC)
    db.commit()
    db.refresh(encounter)
    result = _encounter_responses(db, ctx, [encounter])[0]
    record_audit(
        db,
        action="encounter.finished",
        actor_user_id=ctx.user.id,
        entity="encounter",
        entity_id=encounter.id,
        request=request,
        details={"clinic_id": ctx.clinic.id, "duration_seconds": result.duration_seconds},
    )
    return result


# --- Записи врача ---------------------------------------------------------------------------


@router.post(
    "/encounters/{encounter_id}/records", response_model=ClinicRecordResponse, status_code=status.HTTP_201_CREATED
)
def add_record(
    encounter_id: int, payload: ClinicRecordCreate, request: Request, ctx: DoctorOrAdmin, db: DbSession
) -> ClinicRecordResponse:
    """Добавляет запись в карту питомца: осмотр, анализы, назначение, прививку."""
    encounter = _own_encounter(db, ctx, encounter_id)
    if encounter.status != ENCOUNTER_IN_PROGRESS:
        raise _error(status.HTTP_409_CONFLICT, "encounter_closed", "Приём завершён: новые записи не добавляются")
    now = datetime.now(UTC)
    _require_grant(db, ctx, encounter.pet_id, now, payload.kind)

    occurred_at = payload.occurred_at or now
    _check_not_future(occurred_at, now)

    record = MedicalRecord(
        pet_id=encounter.pet_id,
        kind=payload.kind,
        title=payload.title,
        occurred_at=_as_aware(occurred_at),
        # Название клиники и автор берутся из аккаунта сотрудника: подделать их запросом нельзя.
        clinic_name=ctx.clinic.name,
        author_type=AUTHOR_CLINIC,
        author_user_id=ctx.user.id,
        source=SOURCE_MANUAL,
        description=payload.description,
        diagnosis=payload.diagnosis,
        encounter_id=encounter.id,
    )
    db.add(record)
    db.flush()
    db.add(RecordRevision(record_id=record.id, changed_by_id=ctx.user.id, action="created", snapshot=_snapshot(record)))
    db.commit()
    db.refresh(record)
    result = _single_record_response(db, ctx, record)
    record_audit(
        db,
        action="clinic_record.created",
        actor_user_id=ctx.user.id,
        entity="medical_record",
        entity_id=record.id,
        request=request,
        details={"clinic_id": ctx.clinic.id, "pet_id": encounter.pet_id, "encounter_id": encounter.id, "kind": payload.kind},
    )
    return result


def _visible_record(db: Session, ctx: ClinicContext, record_id: int, now: datetime) -> MedicalRecord:
    """Запись, которую клиника сейчас вправе видеть: есть доступ к питомцу и к разделу этой записи.

    Всё остальное — 404: клиника не должна узнавать о существовании недоступных записей.
    """
    record = db.get(MedicalRecord, record_id)
    grant = _active_grant(db, ctx.clinic.id, record.pet_id, now) if record is not None else None
    if record is None or grant is None or not grant_allows_kind(grant.scopes, record.kind):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
    return record


def _require_authored(db: Session, ctx: ClinicContext, record: MedicalRecord) -> None:
    """Менять запись и добавлять к ней файлы можно только своей клинике."""
    owned = False
    if record.author_type == AUTHOR_CLINIC and record.encounter_id is not None:
        owned = db.scalar(select(Encounter.clinic_id).where(Encounter.id == record.encounter_id)) == ctx.clinic.id
    if not owned:
        raise _error(
            status.HTTP_403_FORBIDDEN, "record_not_editable", "Можно менять только записи, созданные вашей клиникой"
        )


@router.patch("/records/{record_id}", response_model=ClinicRecordResponse)
def edit_record(
    record_id: int, payload: ClinicRecordUpdate, request: Request, ctx: DoctorOrAdmin, db: DbSession
) -> ClinicRecordResponse:
    """Правка своей записи. Прежняя версия сохраняется в истории, владелец её видит."""
    now = datetime.now(UTC)
    record = _visible_record(db, ctx, record_id, now)
    _require_authored(db, ctx, record)

    changes = payload.model_dump(exclude_unset=True)
    for field in ("title", "occurred_at"):
        if field in changes and changes[field] is None:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "field_required", f"Поле «{field}» нельзя очистить"
            )
    if "occurred_at" in changes:
        _check_not_future(changes["occurred_at"], now)
        changes["occurred_at"] = _as_aware(changes["occurred_at"])

    db.add(RecordRevision(record_id=record.id, changed_by_id=ctx.user.id, action="updated", snapshot=_snapshot(record)))
    for key, value in changes.items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    result = _single_record_response(db, ctx, record)
    record_audit(
        db,
        action="clinic_record.updated",
        actor_user_id=ctx.user.id,
        entity="medical_record",
        entity_id=record_id,
        request=request,
        details={"clinic_id": ctx.clinic.id, "fields": sorted(changes)},
    )
    return result


# --- Вложения -------------------------------------------------------------------------------


@router.get("/records/{record_id}/attachments", response_model=list[AttachmentResponse])
def list_attachments(record_id: int, ctx: DoctorOrAdmin, db: DbSession) -> list[RecordAttachment]:
    """Файлы записи. Доступны для любой записи, которую клиника видит в карте пациента."""
    record = _visible_record(db, ctx, record_id, datetime.now(UTC))
    return _attachments_by_record(db, [record.id]).get(record.id, [])


@router.post(
    "/records/{record_id}/attachments", response_model=AttachmentResponse, status_code=status.HTTP_201_CREATED
)
def upload_attachment(
    record_id: int, request: Request, ctx: DoctorOrAdmin, db: DbSession, file: UploadFile = File(...)
) -> AttachmentResponse:
    """Прикрепляет файл (PDF, JPG, PNG до 5 МБ) к своей записи. Тип определяется по содержимому."""
    record = _visible_record(db, ctx, record_id, datetime.now(UTC))
    _require_authored(db, ctx, record)
    count = db.scalar(select(func.count()).select_from(RecordAttachment).where(RecordAttachment.record_id == record.id))
    if (count or 0) >= MAX_ATTACHMENTS_PER_RECORD:
        raise _error(
            status.HTTP_409_CONFLICT,
            "attachments_limit",
            f"К записи можно прикрепить не больше {MAX_ATTACHMENTS_PER_RECORD} файлов",
        )

    # Читаем на байт больше лимита, чтобы отличить «ровно в лимит» от «больше».
    data = file.file.read(MAX_DOCUMENT_BYTES + 1)
    try:
        content_type, extension = detect_document_type(data)
    except DocumentError as exc:
        http_status = (
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            if exc.code == "document_too_large"
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise _error(http_status, exc.code, exc.message) from exc

    attachment = RecordAttachment(
        record_id=record.id,
        filename=safe_filename(file.filename, extension),
        content_type=content_type,
        size_bytes=len(data),
        content=data,
        uploaded_by_id=ctx.user.id,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    result = AttachmentResponse.model_validate(attachment)
    record_audit(
        db,
        action="record_attachment.uploaded",
        actor_user_id=ctx.user.id,
        entity="record_attachment",
        entity_id=attachment.id,
        request=request,
        details={"clinic_id": ctx.clinic.id, "record_id": record_id, "size_bytes": result.size_bytes},
    )
    return result


@router.get("/records/{record_id}/attachments/{attachment_id}/download")
def download_attachment(
    record_id: int, attachment_id: int, request: Request, ctx: DoctorOrAdmin, db: DbSession
) -> Response:
    """Скачивание файла врачом. Каждое скачивание пишется в аудит."""
    record = _visible_record(db, ctx, record_id, datetime.now(UTC))
    attachment = db.scalar(
        select(RecordAttachment)
        .where(RecordAttachment.id == attachment_id, RecordAttachment.record_id == record.id)
        .options(undefer(RecordAttachment.content))
    )
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    # Значения читаем до аудита: record_audit делает commit и сбрасывает состояние объектов.
    content, content_type, filename = attachment.content, attachment.content_type, attachment.filename
    record_audit(
        db,
        action="record_attachment.downloaded",
        actor_user_id=ctx.user.id,
        entity="record_attachment",
        entity_id=attachment_id,
        request=request,
        details={"clinic_id": ctx.clinic.id, "record_id": record_id},
    )
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": content_disposition(filename),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
