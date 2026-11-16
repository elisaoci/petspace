"""Кабинет клиники: заявка организации, профиль, документы и сотрудники.

Права по ролям внутри клиники:

| Действие                                   | admin | doctor | registrar |
| ------------------------------------------ | :---: | :----: | :-------: |
| Профиль клиники и свой статус (`/me`)      |   +   |   +    |     +     |
| Правка данных, документы заявки            |   +   |        |           |
| Список сотрудников                         |   +   |   +    |     +     |
| Приглашение и управление сотрудниками      |   +   |        |           |

Список и управление сотрудниками доступны только у одобренной клиники.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload, undefer

from app.api.auth import _complete_login  # выдача токенов и аудит входа — общие с владельцем
from app.api.clinic_deps import (
    ApprovedClinicMember,
    ClinicContext,
    ClinicMember,
    require_clinic_roles,
    require_clinic_roles_any_status,
)
from app.api.deps import DbSession
from app.api.pagination import PaginationParams, pagination_headers
from app.config import get_settings
from app.models import (
    CLINIC_PENDING,
    CLINIC_REJECTED,
    REQUIRED_CONSENTS,
    ROLE_CLINIC_ADMIN,
    STAFF_ACTIVE,
    STAFF_DISABLED,
    STATUS_ACTIVE,
    STATUS_BLOCKED,
    Clinic,
    ClinicDocument,
    ClinicStaff,
    User,
)
from app.schemas.clinics import (
    ClinicMeResponse,
    ClinicRegisterPayload,
    ClinicRegisterResponse,
    ClinicResponse,
    ClinicUpdatePayload,
    DocumentResponse,
    StaffInvitePayload,
    StaffResponse,
    StaffUpdatePayload,
)
from app.services.audit import client_ip, record_audit
from app.services.clinics import (
    MAX_DOCUMENT_BYTES,
    MAX_DOCUMENTS_PER_CLINIC,
    ROLE_TITLES,
    DocumentError,
    content_disposition,
    detect_document_type,
    notify_application_received,
    notify_staff_invited,
    safe_filename,
)
from app.services.consents import record_consents, validate_consents
from app.services.passwords import hash_password
from app.services.sessions import revoke_all_user_tokens

router = APIRouter(prefix="/clinics", tags=["clinics"])

ClinicAdminAnyStatus = Annotated[ClinicContext, Depends(require_clinic_roles_any_status(ROLE_CLINIC_ADMIN))]
ClinicAdmin = Annotated[ClinicContext, Depends(require_clinic_roles(ROLE_CLINIC_ADMIN))]


# --- Вспомогательное ----------------------------------------------------------------


def staff_response(staff: ClinicStaff) -> StaffResponse:
    return StaffResponse(
        id=staff.id,
        user_id=staff.user_id,
        email=staff.user.email,
        full_name=staff.full_name,
        role=staff.role,
        status=staff.status,
        created_at=staff.created_at,
    )


def clinic_exists(db: Session, inn: str, address: str, *, exclude_id: int | None = None) -> bool:
    """Та же организация по тому же адресу уже есть. Адрес сравниваем без учёта регистра."""
    candidates = db.execute(select(Clinic.id, Clinic.address).where(Clinic.inn == inn)).all()
    wanted = address.casefold()
    return any(row.id != exclude_id and row.address.casefold() == wanted for row in candidates)


def _conflict(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error": code, "message": message})


def _me_response(ctx: ClinicContext) -> ClinicMeResponse:
    base = ClinicResponse.model_validate(ctx.clinic).model_dump()
    return ClinicMeResponse(
        **base,
        my_staff_id=ctx.staff.id,
        my_role=ctx.staff.role,
        my_full_name=ctx.staff.full_name,
    )


def _get_own_document(db: Session, ctx: ClinicContext, document_id: int, *, with_content: bool = False) -> ClinicDocument:
    stmt = select(ClinicDocument).where(ClinicDocument.id == document_id, ClinicDocument.clinic_id == ctx.clinic.id)
    if with_content:
        stmt = stmt.options(undefer(ClinicDocument.content))
    document = db.scalar(stmt)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


# --- Заявка организации ---------------------------------------------------------------


@router.post("/register", response_model=ClinicRegisterResponse, status_code=status.HTTP_201_CREATED)
def register_clinic(payload: ClinicRegisterPayload, request: Request, db: DbSession) -> ClinicRegisterResponse:
    """Подача заявки: создаёт клинику в статусе `pending` и аккаунт её администратора.

    Администратор сразу получает токены: он может загрузить документы и смотреть статус.
    Работа с данными пациентов открывается только после одобрения модератором платформы.
    """
    settings = get_settings()
    pairs = [(item.kind, item.version) for item in payload.consents]

    problems = validate_consents(pairs)
    if problems:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_consents", "problems": problems},
        )
    provided = {kind for kind, _ in pairs}
    missing = [kind for kind in REQUIRED_CONSENTS if kind not in provided]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "consent_required", "kinds": missing, "message": "Примите все согласия"},
        )

    if db.scalar(select(User.id).where(User.email == payload.admin_email)) is not None:
        record_audit(
            db,
            action="clinic.register.rejected",
            entity="clinic",
            request=request,
            details={"email": payload.admin_email, "reason": "email_taken"},
        )
        raise _conflict("email_taken", "Этот email уже зарегистрирован — войдите или укажите другой")

    if clinic_exists(db, payload.inn, payload.address):
        record_audit(
            db,
            action="clinic.register.rejected",
            entity="clinic",
            request=request,
            details={"inn": payload.inn, "reason": "clinic_exists"},
        )
        raise _conflict("clinic_exists", "Заявка для этой организации по этому адресу уже подана")

    now = datetime.now(UTC)
    user = User(
        email=payload.admin_email,
        role=ROLE_CLINIC_ADMIN,
        status=STATUS_ACTIVE,
        password_hash=hash_password(payload.password, settings.password_iterations),
        last_login_at=now,
    )
    clinic = Clinic(
        name=payload.clinic_name,
        inn=payload.inn,
        address=payload.address,
        phone=payload.phone,
        email=payload.email,
        status=CLINIC_PENDING,
    )
    try:
        db.add(user)
        db.flush()
        record_consents(db, user.id, pairs, client_ip(request))
        clinic.created_by_id = user.id
        db.add(clinic)
        db.flush()
        db.add(
            ClinicStaff(
                clinic_id=clinic.id,
                user_id=user.id,
                full_name=payload.contact_name,
                role=ROLE_CLINIC_ADMIN,
                status=STAFF_ACTIVE,
            )
        )
        tokens = _complete_login(db, user, request, settings, action="clinic_admin.registered")
    except IntegrityError as exc:
        # Гонка двух одинаковых заявок: проверки выше прошли у обеих, уникальность поймала вторую.
        db.rollback()
        raise _conflict("clinic_exists", "Такая заявка или такой email уже есть") from exc

    record_audit(
        db,
        action="clinic.registered",
        actor_user_id=user.id,
        entity="clinic",
        entity_id=clinic.id,
        request=request,
        details={"inn": clinic.inn},
    )
    notify_application_received(payload.admin_email, clinic)
    return ClinicRegisterResponse(**tokens.model_dump(), clinic=ClinicResponse.model_validate(clinic))


# --- Профиль клиники ------------------------------------------------------------------


@router.get("/me", response_model=ClinicMeResponse)
def get_my_clinic(ctx: ClinicMember) -> ClinicMeResponse:
    """Клиника текущего сотрудника, её статус модерации и его роль."""
    return _me_response(ctx)


@router.patch("/me", response_model=ClinicMeResponse)
def update_my_clinic(
    payload: ClinicUpdatePayload, request: Request, ctx: ClinicAdminAnyStatus, db: DbSession
) -> ClinicMeResponse:
    clinic = ctx.clinic
    data = payload.model_dump(exclude_unset=True)

    for field in ("name", "inn", "address", "phone"):
        if field in data and data[field] is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": "field_required", "message": f"Поле «{field}» нельзя очистить"},
            )

    if "inn" in data and data["inn"] != clinic.inn and clinic.status not in (CLINIC_PENDING, CLINIC_REJECTED):
        raise _conflict("inn_locked", "ИНН подтверждённой клиники менять нельзя — обратитесь в поддержку")

    new_inn = data.get("inn", clinic.inn)
    new_address = data.get("address", clinic.address)
    if ("inn" in data or "address" in data) and clinic_exists(db, new_inn, new_address, exclude_id=clinic.id):
        raise _conflict("clinic_exists", "Клиника с таким ИНН и адресом уже есть")

    for key, value in data.items():
        setattr(clinic, key, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _conflict("clinic_exists", "Клиника с таким ИНН и адресом уже есть") from exc
    db.refresh(clinic)
    record_audit(
        db,
        action="clinic.updated",
        actor_user_id=ctx.user.id,
        entity="clinic",
        entity_id=clinic.id,
        request=request,
        details={"fields": sorted(data)},
    )
    return _me_response(ctx)


@router.post("/me/resubmit", response_model=ClinicMeResponse)
def resubmit_my_clinic(request: Request, ctx: ClinicAdminAnyStatus, db: DbSession) -> ClinicMeResponse:
    """Повторная отправка отклонённой заявки после исправлений."""
    clinic = ctx.clinic
    if clinic.status != CLINIC_REJECTED:
        raise _conflict("invalid_status", "Повторно отправить можно только отклонённую заявку")
    clinic.status = CLINIC_PENDING
    clinic.status_reason = None
    db.commit()
    db.refresh(clinic)
    record_audit(
        db,
        action="clinic.resubmitted",
        actor_user_id=ctx.user.id,
        entity="clinic",
        entity_id=clinic.id,
        request=request,
    )
    return _me_response(ctx)


# --- Документы заявки -----------------------------------------------------------------


@router.get("/me/documents", response_model=list[DocumentResponse])
def list_my_documents(ctx: ClinicMember, db: DbSession) -> list[ClinicDocument]:
    return list(
        db.scalars(
            select(ClinicDocument).where(ClinicDocument.clinic_id == ctx.clinic.id).order_by(ClinicDocument.id)
        ).all()
    )


@router.post("/me/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def upload_my_document(
    request: Request,
    ctx: ClinicAdminAnyStatus,
    db: DbSession,
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=200),
) -> ClinicDocument:
    """Загрузка документа (PDF, JPG или PNG до 5 МБ). Тип определяется по содержимому файла."""
    count = db.scalar(select(func.count()).select_from(ClinicDocument).where(ClinicDocument.clinic_id == ctx.clinic.id))
    if (count or 0) >= MAX_DOCUMENTS_PER_CLINIC:
        raise _conflict("documents_limit", f"Можно загрузить не больше {MAX_DOCUMENTS_PER_CLINIC} документов")

    # Читаем на байт больше лимита: так отличаем «ровно в лимит» от «больше».
    data = file.file.read(MAX_DOCUMENT_BYTES + 1)
    try:
        content_type, extension = detect_document_type(data)
    except DocumentError as exc:
        http_status = (
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            if exc.code == "document_too_large"
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=http_status, detail={"error": exc.code, "message": exc.message}) from exc

    filename = safe_filename(file.filename, extension)
    document = ClinicDocument(
        clinic_id=ctx.clinic.id,
        title=(title or "").strip() or filename,
        filename=filename,
        content_type=content_type,
        size_bytes=len(data),
        content=data,
        uploaded_by_id=ctx.user.id,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    record_audit(
        db,
        action="clinic.document.uploaded",
        actor_user_id=ctx.user.id,
        entity="clinic_document",
        entity_id=document.id,
        request=request,
        details={"clinic_id": ctx.clinic.id, "size_bytes": document.size_bytes},
    )
    return document


@router.get("/me/documents/{document_id}/download")
def download_my_document(document_id: int, ctx: ClinicAdminAnyStatus, db: DbSession) -> Response:
    document = _get_own_document(db, ctx, document_id, with_content=True)
    return Response(
        content=document.content,
        media_type=document.content_type,
        headers={
            "Content-Disposition": content_disposition(document.filename),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/me/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_document(document_id: int, request: Request, ctx: ClinicAdminAnyStatus, db: DbSession) -> Response:
    if ctx.clinic.status not in (CLINIC_PENDING, CLINIC_REJECTED):
        raise _conflict("documents_locked", "Документы подтверждённой клиники удалить нельзя")
    document = _get_own_document(db, ctx, document_id)
    document_id_value = document.id
    db.delete(document)
    db.commit()
    record_audit(
        db,
        action="clinic.document.deleted",
        actor_user_id=ctx.user.id,
        entity="clinic_document",
        entity_id=document_id_value,
        request=request,
        details={"clinic_id": ctx.clinic.id},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Сотрудники -----------------------------------------------------------------------


@router.get("/me/staff", response_model=list[StaffResponse])
def list_staff(ctx: ApprovedClinicMember, pagination: PaginationParams, response: Response, db: DbSession):
    total = db.scalar(select(func.count()).select_from(ClinicStaff).where(ClinicStaff.clinic_id == ctx.clinic.id)) or 0
    rows = db.scalars(
        select(ClinicStaff)
        .where(ClinicStaff.clinic_id == ctx.clinic.id)
        .options(selectinload(ClinicStaff.user))
        .order_by(ClinicStaff.id)
        .limit(pagination.limit)
        .offset(pagination.offset)
    ).all()
    pagination_headers(response, total=total, pagination=pagination)
    return [staff_response(staff) for staff in rows]


@router.post("/me/staff", response_model=StaffResponse, status_code=status.HTTP_201_CREATED)
def invite_staff(payload: StaffInvitePayload, request: Request, ctx: ClinicAdmin, db: DbSession) -> StaffResponse:
    """Добавляет сотрудника без пароля и отправляет приглашение.

    Пароль сотрудник задаёт сам через «Забыли пароль» на странице входа: так пароль
    никогда не передаётся администратором и не лежит в письме.
    """
    if db.scalar(select(User.id).where(User.email == payload.email)) is not None:
        raise _conflict("email_taken", "Этот email уже зарегистрирован в PetSpace")

    user = User(email=payload.email, role=payload.role, status=STATUS_ACTIVE)
    try:
        db.add(user)
        db.flush()
        staff = ClinicStaff(
            clinic_id=ctx.clinic.id,
            user_id=user.id,
            full_name=payload.full_name,
            role=payload.role,
            status=STAFF_ACTIVE,
        )
        db.add(staff)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _conflict("email_taken", "Этот email уже зарегистрирован в PetSpace") from exc

    db.refresh(staff)
    record_audit(
        db,
        action="clinic.staff.invited",
        actor_user_id=ctx.user.id,
        entity="clinic_staff",
        entity_id=staff.id,
        request=request,
        details={"clinic_id": ctx.clinic.id, "role": payload.role},
    )
    notify_staff_invited(payload.email, ctx.clinic, ROLE_TITLES[payload.role])
    return staff_response(staff)


@router.patch("/me/staff/{staff_id}", response_model=StaffResponse)
def update_staff(
    staff_id: int, payload: StaffUpdatePayload, request: Request, ctx: ClinicAdmin, db: DbSession
) -> StaffResponse:
    """Меняет имя, роль или статус сотрудника своей клиники.

    Нельзя менять самого себя: так в клинике всегда остаётся хотя бы один активный администратор.
    Отключённый сотрудник теряет вход сразу, его сессии отзываются.
    """
    staff = db.scalar(
        select(ClinicStaff)
        .where(ClinicStaff.id == staff_id, ClinicStaff.clinic_id == ctx.clinic.id)
        .options(selectinload(ClinicStaff.user))
    )
    if staff is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found")
    if staff.id == ctx.staff.id:
        raise _conflict("cannot_modify_self", "Свою роль и статус менять нельзя — попросите другого администратора")

    changes = {key: value for key, value in payload.model_dump(exclude_unset=True).items() if value is not None}
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "nothing_to_change", "message": "Укажите, что изменить"},
        )

    if "full_name" in changes:
        staff.full_name = changes["full_name"]
    if "role" in changes:
        staff.role = changes["role"]
        staff.user.role = changes["role"]

    disabled_now = False
    if changes.get("status") == STAFF_DISABLED and staff.status == STAFF_ACTIVE:
        staff.status = STAFF_DISABLED
        staff.user.status = STATUS_BLOCKED
        disabled_now = True
    elif changes.get("status") == STAFF_ACTIVE and staff.status == STAFF_DISABLED:
        staff.status = STAFF_ACTIVE
        staff.user.status = STATUS_ACTIVE

    db.commit()
    if disabled_now:
        revoke_all_user_tokens(db, staff.user_id)
    db.refresh(staff)
    record_audit(
        db,
        action="clinic.staff.updated",
        actor_user_id=ctx.user.id,
        entity="clinic_staff",
        entity_id=staff.id,
        request=request,
        details={"clinic_id": ctx.clinic.id, "fields": sorted(changes)},
    )
    return staff_response(staff)
