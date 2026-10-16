"""Журнал доступа к данным (аудит).

Пишем входы, обновление токенов, обращения к публичной медкарте и изменения данных
питомца. Доступ клиник к медзаписям будет логироваться здесь же.
"""

from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog

ACTOR_USER = "user"
ACTOR_ANONYMOUS = "anonymous"


def client_ip(request: Request | None) -> str | None:
    """Учитывает X-Forwarded-For: за Nginx request.client.host — это адрес прокси."""
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def record_audit(
    db: Session,
    *,
    action: str,
    actor_user_id: int | None = None,
    actor_type: str = ACTOR_USER,
    entity: str | None = None,
    entity_id: int | None = None,
    request: Request | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            action=action,
            entity=entity,
            entity_id=entity_id,
            ip=client_ip(request),
            user_agent=(request.headers.get("user-agent") if request else None),
            details=details,
        )
    )
    db.commit()
