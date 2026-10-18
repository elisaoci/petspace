"""Админка платформы: доступ только для роли platform_admin.

Пока это журнал аудита и список пользователей — минимум, который нужен для проверки
RBAC и для операций пилота (подтверждение клиник появится вместе с кабинетом клиники).
"""

from datetime import datetime

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import DbSession, PlatformAdmin
from app.api.pagination import PaginationParams, pagination_headers
from app.models import AuditLog, User

router = APIRouter(prefix="/admin", tags=["admin"])


class AuditLogResponse(BaseModel):
    id: int
    actor_user_id: int | None
    actor_type: str
    action: str
    entity: str | None
    entity_id: int | None
    ip: str | None
    created_at: datetime


class AdminUserResponse(BaseModel):
    id: int
    email: str | None
    phone: str | None
    role: str
    status: str
    created_at: datetime
    last_login_at: datetime | None


@router.get("/audit", response_model=list[AuditLogResponse])
def list_audit_log(
    admin: PlatformAdmin,
    pagination: PaginationParams,
    response: Response,
    db: DbSession,
) -> list[AuditLog]:
    """Журнал доступа к данным, новые события первыми."""
    total = db.scalar(select(func.count()).select_from(AuditLog)) or 0
    rows = db.scalars(
        select(AuditLog).order_by(AuditLog.id.desc()).limit(pagination.limit).offset(pagination.offset)
    ).all()
    pagination_headers(response, total=total, pagination=pagination)
    return list(rows)


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(
    admin: PlatformAdmin,
    pagination: PaginationParams,
    response: Response,
    db: DbSession,
) -> list[User]:
    total = db.scalar(select(func.count()).select_from(User)) or 0
    rows = db.scalars(
        select(User).order_by(User.id).limit(pagination.limit).offset(pagination.offset)
    ).all()
    pagination_headers(response, total=total, pagination=pagination)
    return list(rows)
