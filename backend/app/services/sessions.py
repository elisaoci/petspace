"""Жизненный цикл сессий: выдача, ротация и отзыв refresh-токенов.

Ротация обязательна: каждый refresh одноразовый. Повторное использование старого
токена означает, что он был украден, поэтому отзываются все сессии пользователя.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import STATUS_ACTIVE, RefreshToken, User
from app.services.security import (
    create_access_token,
    generate_refresh_token,
    hash_token,
)

REASON_UNKNOWN = "unknown"
REASON_EXPIRED = "expired"
REASON_REUSED = "reused"
REASON_USER_INACTIVE = "user_inactive"


class RefreshError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _store_refresh_token(
    db: Session,
    user_id: int,
    settings: Settings,
    *,
    ip: str | None,
    user_agent: str | None,
) -> str:
    raw_token = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
            ip=ip,
            user_agent=(user_agent or "")[:255] or None,
        )
    )
    return raw_token


def issue_token_pair(
    db: Session,
    user: User,
    settings: Settings,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[str, str, int]:
    """Возвращает (access_token, refresh_token, expires_in в секундах)."""
    access_token = create_access_token(user.id, settings)
    refresh_token = _store_refresh_token(db, user.id, settings, ip=ip, user_agent=user_agent)
    return access_token, refresh_token, settings.access_token_ttl_minutes * 60


def rotate_refresh_token(
    db: Session,
    raw_token: str,
    settings: Settings,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[User, str, str, int]:
    """Гасит старый refresh-токен и выдаёт новую пару."""
    stored = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    if stored is None:
        raise RefreshError(REASON_UNKNOWN)

    if stored.revoked_at is not None:
        # Токен уже использовали: считаем это кражей и закрываем все сессии пользователя.
        revoke_all_user_tokens(db, stored.user_id)
        raise RefreshError(REASON_REUSED)

    if stored.expires_at <= datetime.now(UTC):
        raise RefreshError(REASON_EXPIRED)

    user = db.get(User, stored.user_id)
    if user is None or user.status != STATUS_ACTIVE:
        raise RefreshError(REASON_USER_INACTIVE)

    stored.revoked_at = datetime.now(UTC)
    access_token, refresh_token, expires_in = issue_token_pair(
        db, user, settings, ip=ip, user_agent=user_agent
    )
    db.flush()
    stored.replaced_by_id = db.scalar(
        select(RefreshToken.id)
        .where(RefreshToken.token_hash == hash_token(refresh_token))
        .limit(1)
    )
    db.commit()
    return user, access_token, refresh_token, expires_in


def revoke_refresh_token(db: Session, raw_token: str) -> bool:
    stored = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    if stored is None or stored.revoked_at is not None:
        return False
    stored.revoked_at = datetime.now(UTC)
    db.commit()
    return True


def revoke_all_user_tokens(db: Session, user_id: int) -> int:
    result = db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    db.commit()
    return result.rowcount or 0
