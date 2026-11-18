"""Вложения к медзаписям глазами владельца: смотреть, скачивать, удалять.

Владелец видит файлы всех записей своего питомца, в том числе добавленные клиниками.
Загружают файлы врачи (`POST /clinics/me/records/{id}/attachments`), владелец только читает
и может удалить файл, который считает лишним.
"""

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, undefer

from app.api.deps import CurrentUser, DbSession
from app.api.records import _owned_record  # проверка, что запись принадлежит питомцу владельца
from app.models import RecordAttachment
from app.schemas.encounters import AttachmentResponse
from app.services.audit import record_audit
from app.services.clinics import content_disposition

router = APIRouter(tags=["records"])


def _attachment(db: Session, record_id: int, attachment_id: int, *, with_content: bool = False) -> RecordAttachment:
    stmt = select(RecordAttachment).where(
        RecordAttachment.id == attachment_id, RecordAttachment.record_id == record_id
    )
    if with_content:
        stmt = stmt.options(undefer(RecordAttachment.content))
    attachment = db.scalar(stmt)
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    return attachment


@router.get("/records/{record_id}/attachments", response_model=list[AttachmentResponse])
def list_attachments(record_id: int, user: CurrentUser, db: DbSession) -> list[RecordAttachment]:
    record = _owned_record(record_id, user, db)
    return list(
        db.scalars(
            select(RecordAttachment).where(RecordAttachment.record_id == record.id).order_by(RecordAttachment.id)
        ).all()
    )


@router.get("/records/{record_id}/attachments/{attachment_id}/download")
def download_attachment(record_id: int, attachment_id: int, user: CurrentUser, db: DbSession) -> Response:
    record = _owned_record(record_id, user, db)
    attachment = _attachment(db, record.id, attachment_id, with_content=True)
    return Response(
        content=attachment.content,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": content_disposition(attachment.filename),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/records/{record_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    record_id: int, attachment_id: int, request: Request, user: CurrentUser, db: DbSession
) -> Response:
    record = _owned_record(record_id, user, db)
    attachment = _attachment(db, record.id, attachment_id)
    attachment_id_value = attachment.id
    db.delete(attachment)
    db.commit()
    record_audit(
        db,
        action="record_attachment.deleted",
        actor_user_id=user.id,
        entity="record_attachment",
        entity_id=attachment_id_value,
        request=request,
        details={"record_id": record_id},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
