"""Доступ клиники к пациенту: запросы доступа и одноразовые коды владельца.

Два пути к одному результату — активной записи `AccessGrant` с привязкой к клинике:

1. **Код.** Владелец в приложении создаёт короткий код (он же QR), называет его в клинике,
   клиника вводит код — доступ открывается сразу: владелец сам его инициировал.
2. **Запрос.** Клиника указывает имя питомца и телефон владельца, владелец получает запрос
   и подтверждает или отклоняет его в приложении. Пока владелец не подтвердил, данных нет.

Срок действия запроса не хранится как статус: `pending` с истёкшим `expires_at` считается
`expired` на лету (как `overdue` у событий календаря), отдельная фоновая задача не нужна.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.services.crypto import EncryptedText

REQUEST_PENDING = "pending"
REQUEST_APPROVED = "approved"
REQUEST_DENIED = "denied"
REQUEST_EXPIRED = "expired"  # вычисляется, в базе не хранится
REQUEST_CANCELLED = "cancelled"
REQUEST_STATUSES = (REQUEST_PENDING, REQUEST_APPROVED, REQUEST_DENIED, REQUEST_EXPIRED, REQUEST_CANCELLED)


class AccessRequest(Base):
    """Запрос клиники на доступ к карте питомца.

    `pet_id` пуст, если по имени и телефону никого не нашлось. Строка создаётся в любом случае:
    так клиника не может по ответу API отличить «питомца нет» от «владелец ещё не ответил»
    и перебирать чужие номера телефонов.
    """

    __tablename__ = "access_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"), index=True, nullable=False
    )
    requested_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    pet_id: Mapped[int | None] = mapped_column(ForeignKey("pets.id", ondelete="CASCADE"), index=True)
    # Что ввёл сотрудник клиники: имя как набрано и телефон в нормализованном виде.
    pet_name_query: Mapped[str] = mapped_column(String(120), nullable=False)
    owner_phone_query: Mapped[str] = mapped_column(String(32), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    ttl_days: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str | None] = mapped_column(EncryptedText)
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default=REQUEST_PENDING)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    grant_id: Mapped[int | None] = mapped_column(ForeignKey("access_grants.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def effective_status(self, now: datetime) -> str:
        if self.status == REQUEST_PENDING and self.expires_at <= now:
            return REQUEST_EXPIRED
        return self.status

    def describe(self) -> dict[str, Any]:
        return {"clinic_id": self.clinic_id, "pet_id": self.pet_id, "scopes": self.scopes}


class AccessCode(Base):
    """Одноразовый короткий код доступа, который владелец показывает клинике.

    В базе лежит только HMAC-хэш кода. Код живёт считаные минуты, используется один раз,
    а новый код питомца аннулирует прежний неиспользованный.
    """

    __tablename__ = "access_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey("pets.id", ondelete="CASCADE"), index=True, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    code_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    # Какие разделы и на сколько дней откроются клинике после ввода кода.
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    ttl_days: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used_by_clinic_id: Mapped[int | None] = mapped_column(ForeignKey("clinics.id", ondelete="SET NULL"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def is_usable(self, now: datetime) -> bool:
        return self.used_at is None and self.revoked_at is None and self.expires_at > now
