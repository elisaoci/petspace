"""Модели авторизации, согласий и аудита.

Отдельный модуль от `entities.py`, чтобы доменные модели питомцев не разрастались.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Роли пользователя. Роли клиник (clinic_admin, clinic_doctor, clinic_registrar)
# появятся вместе с кабинетом клиники.
ROLE_OWNER = "owner"
ROLE_PLATFORM_ADMIN = "platform_admin"

STATUS_ACTIVE = "active"
STATUS_BLOCKED = "blocked"

# Версии текстов согласий. Меняются вместе с юридическими документами.
CONSENT_TERMS = "terms"
CONSENT_PRIVACY = "privacy"
CONSENT_VERSIONS = {CONSENT_TERMS: "2026-01-01", CONSENT_PRIVACY: "2026-01-01"}
REQUIRED_CONSENTS = (CONSENT_TERMS, CONSENT_PRIVACY)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default=ROLE_OWNER)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=STATUS_ACTIVE)
    # PBKDF2-хэш в формате algo$iterations$salt$hash; NULL у аккаунтов,
    # созданных до появления паролей (входят по коду).
    password_hash: Mapped[str | None] = mapped_column(String(255))
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OtpCode(Base):
    """Одноразовый код входа. Хранится только HMAC-хэш: утечка БД не даёт войти."""

    __tablename__ = "otp_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    destination: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, default="login")
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RefreshToken(Base):
    """Refresh-токен хранится хэшем. Ротация: старая запись помечается revoked_at
    и ссылается на замену через replaced_by_id. Повторное использование отозванного
    токена трактуется как кража и отзывает все сессии пользователя.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[int | None] = mapped_column(Integer)
    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Consent(Base):
    """Согласие пользователя с конкретной версией текста (152-ФЗ)."""

    __tablename__ = "consents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ip: Mapped[str | None] = mapped_column(String(64))


class AuditLog(Base):
    """Журнал доступа к данным: кто, что и когда смотрел или менял."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    action: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    entity: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
