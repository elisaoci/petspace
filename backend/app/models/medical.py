"""Smart-ID: медицинские записи питомца и доступ к ним по ссылке.

Каждая запись знает автора (владелец или клиника) и источник (ручной ввод или МИС).
Тексты жалоб, описаний и диагнозов шифруются.

Доступ выдаётся длинным токеном с набором разделов, сроком действия и возможностью
отзыва. Сырой токен показывается один раз, в базе лежит только хэш.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.services.crypto import EncryptedText

# Виды записей
RECORD_VISIT = "visit"
RECORD_VACCINATION = "vaccination"
RECORD_LAB = "lab"
RECORD_PRESCRIPTION = "prescription"
RECORD_OTHER = "other"
RECORD_KINDS = (RECORD_VISIT, RECORD_VACCINATION, RECORD_LAB, RECORD_PRESCRIPTION, RECORD_OTHER)

# Кто создал запись
AUTHOR_OWNER = "owner"
AUTHOR_CLINIC = "clinic"
AUTHOR_TYPES = (AUTHOR_OWNER, AUTHOR_CLINIC)

# Откуда пришла запись
SOURCE_MANUAL = "manual"
SOURCE_MIS = "mis"
RECORD_SOURCES = (SOURCE_MANUAL, SOURCE_MIS)

# Разделы, которые можно открыть по ссылке
SCOPE_PROFILE = "profile"
SCOPE_RECORDS = "records"
SCOPE_VACCINATIONS = "vaccinations"
ACCESS_SCOPES = (SCOPE_PROFILE, SCOPE_RECORDS, SCOPE_VACCINATIONS)
DEFAULT_SCOPES = [SCOPE_PROFILE, SCOPE_RECORDS, SCOPE_VACCINATIONS]


class MedicalRecord(Base):
    __tablename__ = "medical_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pet_id: Mapped[int] = mapped_column(
        ForeignKey("pets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default=RECORD_VISIT)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    clinic_name: Mapped[str | None] = mapped_column(String(200))
    author_type: Mapped[str] = mapped_column(String(16), nullable=False, default=AUTHOR_OWNER)
    author_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(16), nullable=False, default=SOURCE_MANUAL)
    external_id: Mapped[str | None] = mapped_column(String(128))
    # Жалобы, описание приёма, результаты — медицинские данные, шифруются.
    description: Mapped[str | None] = mapped_column(EncryptedText)
    diagnosis: Mapped[str | None] = mapped_column(EncryptedText)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    revisions: Mapped[list["RecordRevision"]] = relationship(
        back_populates="record", cascade="all, delete-orphan"
    )


class RecordRevision(Base):
    """История изменений: снимок прежнего состояния записи.

    Снимок тоже медицинские данные, поэтому хранится зашифрованным (JSON-строка).
    """

    __tablename__ = "record_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("medical_records.id", ondelete="CASCADE"), index=True, nullable=False
    )
    changed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    snapshot: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    record: Mapped[MedicalRecord] = relationship(back_populates="revisions")


class AccessGrant(Base):
    """Выданный доступ к медкарте: кому, какие разделы, до какого срока.

    `token_hash` — SHA-256 от токена: сам токен не хранится, показывается один раз.
    """

    __tablename__ = "access_grants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pet_id: Mapped[int] = mapped_column(
        ForeignKey("pets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def is_active(self, now: datetime) -> bool:
        return self.revoked_at is None and self.expires_at > now

    def has_scope(self, scope: str) -> bool:
        return scope in (self.scopes or [])

    def describe(self) -> dict[str, Any]:
        return {"label": self.label, "expires_at": self.expires_at, "scopes": self.scopes}
