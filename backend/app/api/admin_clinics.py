"""Модерация клиник: очередь заявок, документы, одобрение, отказ, приостановка.

Доступно только роли `platform_admin`. Каждое решение пишется в журнал аудита,
а клиника получает письмо с результатом (при отказе и приостановке — с причиной).
"""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload, undefer

from app.api.clinics import staff_response
from app.api.deps import DbSession, PlatformAdmin
from app.api.pagination import PaginationParams, pagination_headers
from app.models import (
    CLINIC_APPROVED,
    CLINIC_PENDING,
    CLINIC_REJECTED,
    CLINIC_SUSPENDED,
    ROLE_CLINIC_ADMIN,
    STAFF_ACTIVE,
    Clinic,
    ClinicDocument,
    ClinicStaff,
    User,
)
from app.schemas.clinics import (
    AdminClinicDetail,
    AdminClinicListItem,
    ClinicResponse,
    DocumentResponse,
    ModerationReasonPayload,
)
from app.services.audit import record_audit
from app.services.clinics import (
    content_disposition,
    notify_clinic_approved,
    notify_clinic_rejected,
    notify_clinic_suspended,
)

router = APIRouter(prefix="/admin/clinics", tags=["admin"])

StatusFilter = Literal["pending", "approved", "rejected", "suspended"]


def _get_clinic(db: Session, clinic_id: int) -> Clinic:
    clinic = db.get(Clinic, clinic_id)
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinic not found")
    return clinic


def _admin_emails(db: Session, clinic_id: int) -> list[str]:
    """Кому писать о решении: активные администраторы клиники."""
    rows = db.scalars(
        select(User.email)
        .join(ClinicStaff, ClinicStaff.user_id == User.id)
        .where(
            ClinicStaff.clinic_id == clinic_id,
            ClinicStaff.role == ROLE_CLINIC_ADMIN,
            ClinicStaff.status == STAFF_ACTIVE,
            User.email.is_not(None),
        )
    ).all()
    return list(rows)


def _transition(
    db: Session,
    clinic: Clinic,
    admin: User,
    *,
    allowed_from: tuple[str, ...],
    to: str,
    reason: str | None,
) -> str:
    """Меняет статус клиники по допустимому переходу. Возвращает прежний статус."""
    if clinic.status not in allowed_from:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "invalid_status",
                "message": "Из текущего статуса этот переход невозможен",
                "current": clinic.status,
                "allowed_from": list(allowed_from),
            },
        )
    previous = clinic.status
    clinic.status = to
    clinic.status_reason = reason
    clinic.moderated_by_id = admin.id
    clinic.moderated_at = datetime.now(UTC)
    db.commit()
    db.refresh(clinic)
    return previous


@router.get("", response_model=list[AdminClinicListItem])
def list_clinics(
    admin: PlatformAdmin,
    pagination: PaginationParams,
    response: Response,
    db: DbSession,
    status_filter: StatusFilter | None = Query(default=None, alias="status", description="Статус клиники"),
    q: str | None = Query(default=None, max_length=100, description="Поиск по названию или началу ИНН"),
):
    """Очередь модерации. С фильтром `status=pending` заявки идут от старых к новым."""
    conditions = []
    if status_filter:
        conditions.append(Clinic.status == status_filter)
    if q and q.strip():
        term = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(or_(Clinic.name.ilike(f"%{term}%", escape="\\"), Clinic.inn.like(f"{term}%", escape="\\")))

    total = db.scalar(select(func.count()).select_from(Clinic).where(*conditions)) or 0
    order = Clinic.id.asc() if status_filter == CLINIC_PENDING else Clinic.id.desc()
    clinics = db.scalars(
        select(Clinic).where(*conditions).order_by(order).limit(pagination.limit).offset(pagination.offset)
    ).all()

    ids = [clinic.id for clinic in clinics]
    staff_counts: dict[int, int] = {}
    document_counts: dict[int, int] = {}
    if ids:
        staff_counts = dict(
            db.execute(
                select(ClinicStaff.clinic_id, func.count())
                .where(ClinicStaff.clinic_id.in_(ids))
                .group_by(ClinicStaff.clinic_id)
            ).all()
        )
        document_counts = dict(
            db.execute(
                select(ClinicDocument.clinic_id, func.count())
                .where(ClinicDocument.clinic_id.in_(ids))
                .group_by(ClinicDocument.clinic_id)
            ).all()
        )

    pagination_headers(response, total=total, pagination=pagination)
    return [
        AdminClinicListItem(
            **ClinicResponse.model_validate(clinic).model_dump(),
            staff_count=staff_counts.get(clinic.id, 0),
            documents_count=document_counts.get(clinic.id, 0),
        )
        for clinic in clinics
    ]


@router.get("/{clinic_id}", response_model=AdminClinicDetail)
def get_clinic(clinic_id: int, admin: PlatformAdmin, db: DbSession) -> AdminClinicDetail:
    clinic = _get_clinic(db, clinic_id)
    staff = db.scalars(
        select(ClinicStaff)
        .where(ClinicStaff.clinic_id == clinic.id)
        .options(selectinload(ClinicStaff.user))
        .order_by(ClinicStaff.id)
    ).all()
    documents = db.scalars(
        select(ClinicDocument).where(ClinicDocument.clinic_id == clinic.id).order_by(ClinicDocument.id)
    ).all()
    created_by = db.get(User, clinic.created_by_id) if clinic.created_by_id else None
    moderated_by = db.get(User, clinic.moderated_by_id) if clinic.moderated_by_id else None
    return AdminClinicDetail(
        **ClinicResponse.model_validate(clinic).model_dump(),
        created_by_email=created_by.email if created_by else None,
        moderated_by_email=moderated_by.email if moderated_by else None,
        staff=[staff_response(member) for member in staff],
        documents=[DocumentResponse.model_validate(document) for document in documents],
    )


@router.get("/{clinic_id}/documents/{document_id}/download")
def download_document(
    clinic_id: int, document_id: int, request: Request, admin: PlatformAdmin, db: DbSession
) -> Response:
    """Скачивание документа модератором. Каждое скачивание фиксируется в аудите."""
    document = db.scalar(
        select(ClinicDocument)
        .where(ClinicDocument.id == document_id, ClinicDocument.clinic_id == clinic_id)
        .options(undefer(ClinicDocument.content))
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    # Значения читаем до аудита: record_audit делает commit и сбрасывает состояние объекта.
    content, content_type, filename, document_id_value = (
        document.content,
        document.content_type,
        document.filename,
        document.id,
    )
    record_audit(
        db,
        action="clinic.document.downloaded",
        actor_user_id=admin.id,
        entity="clinic_document",
        entity_id=document_id_value,
        request=request,
        details={"clinic_id": clinic_id},
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


@router.post("/{clinic_id}/approve", response_model=ClinicResponse)
def approve_clinic(clinic_id: int, request: Request, admin: PlatformAdmin, db: DbSession) -> Clinic:
    """Одобряет заявку или возвращает приостановленную клинику к работе."""
    clinic = _get_clinic(db, clinic_id)
    previous = _transition(
        db,
        clinic,
        admin,
        allowed_from=(CLINIC_PENDING, CLINIC_REJECTED, CLINIC_SUSPENDED),
        to=CLINIC_APPROVED,
        reason=None,
    )
    record_audit(
        db,
        action="clinic.approved",
        actor_user_id=admin.id,
        entity="clinic",
        entity_id=clinic.id,
        request=request,
        details={"from": previous},
    )
    for email in _admin_emails(db, clinic.id):
        notify_clinic_approved(email, clinic)
    return clinic


@router.post("/{clinic_id}/reject", response_model=ClinicResponse)
def reject_clinic(
    clinic_id: int, payload: ModerationReasonPayload, request: Request, admin: PlatformAdmin, db: DbSession
) -> Clinic:
    """Отклоняет заявку на проверке. Причина обязательна: её увидит клиника."""
    clinic = _get_clinic(db, clinic_id)
    _transition(db, clinic, admin, allowed_from=(CLINIC_PENDING,), to=CLINIC_REJECTED, reason=payload.reason)
    record_audit(
        db,
        action="clinic.rejected",
        actor_user_id=admin.id,
        entity="clinic",
        entity_id=clinic.id,
        request=request,
        details={"reason": payload.reason},
    )
    for email in _admin_emails(db, clinic.id):
        notify_clinic_rejected(email, clinic)
    return clinic


@router.post("/{clinic_id}/suspend", response_model=ClinicResponse)
def suspend_clinic(
    clinic_id: int, payload: ModerationReasonPayload, request: Request, admin: PlatformAdmin, db: DbSession
) -> Clinic:
    """Приостанавливает работу одобренной клиники: доступ к данным пациентов закрывается сразу."""
    clinic = _get_clinic(db, clinic_id)
    _transition(db, clinic, admin, allowed_from=(CLINIC_APPROVED,), to=CLINIC_SUSPENDED, reason=payload.reason)
    record_audit(
        db,
        action="clinic.suspended",
        actor_user_id=admin.id,
        entity="clinic",
        entity_id=clinic.id,
        request=request,
        details={"reason": payload.reason},
    )
    for email in _admin_emails(db, clinic.id):
        notify_clinic_suspended(email, clinic)
    return clinic

