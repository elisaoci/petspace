"""Клиники: организация, документы заявки и сотрудники.

Жизненный цикл клиники:

    pending ──approve──▶ approved ──suspend──▶ suspended
       │                    ▲                      │
       └──reject──▶ rejected ──resubmit──▶ pending │
                                  approve ◀────────┘

Работать с данными пациентов (следующие этапы) клиника может только в статусе `approved`.
Сотрудник — это обычный `User` с ролью `clinic_*` и записью в `clinic_staff`.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.auth import ROLE_CLINIC_ADMIN, ROLE_CLINIC_DOCTOR, ROLE_CLINIC_REGISTRAR, User

CLINIC_PENDING = "pending"
CLINIC_APPROVED = "approved"
CLINIC_REJECTED = "rejected"
CLINIC_SUSPENDED = "suspended"
CLINIC_STATUSES = (CLINIC_PENDING, CLINIC_APPROVED, CLINIC_REJECTED, CLINIC_SUSPENDED)

STAFF_ACTIVE = "active"
STAFF_DISABLED = "disabled"
STAFF_STATUSES = (STAFF_ACTIVE, STAFF_DISABLED)

# Роли, которые можно назначить сотруднику клиники.
CLINIC_STAFF_ROLES = (ROLE_CLINIC_ADMIN, ROLE_CLINIC_DOCTOR, ROLE_CLINIC_REGISTRAR)


class Clinic(Base):
    __tablename__ = "clinics"
    # У сети клиник один ИНН на несколько адресов, поэтому уникальна пара ИНН + адрес.
    __table_args__ = (UniqueConstraint("inn", "address", name="uq_clinics_inn_address"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    inn: Mapped[str] = mapped_column(String(12), index=True, nullable=False)
    address: Mapped[str] = mapped_column(String(300), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), index=True, nullable=False, default=CLINIC_PENDING)
    # Причина отказа или приостановки: её видит сама клиника.
    status_reason: Mapped[str | None] = mapped_column(String(1000))
    moderated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    staff: Mapped[list["ClinicStaff"]] = relationship(back_populates="clinic", cascade="all, delete-orphan")
    documents: Mapped[list["ClinicDocument"]] = relationship(back_populates="clinic", cascade="all, delete-orphan")


class ClinicDocument(Base):
    """Документ к заявке (лицензия, выписка из ЕГРЮЛ и т.п.).

    Файл лежит в БД, а не в `uploads/`: эта папка раздаётся наружу без авторизации,
    а документы организации должен видеть только модератор и сама клиника.
    Для пилота этого достаточно; при росте объёма переезжает в объектное хранилище.
    """

    __tablename__ = "clinic_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    # deferred: в списках документов тело файла не грузится.
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    clinic: Mapped[Clinic] = relationship(back_populates="documents")


class ClinicStaff(Base):
    """Членство пользователя в клинике. Один пользователь состоит в одной клинике."""

    __tablename__ = "clinic_staff"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Дублирует User.role: по User.role работает require_roles, по этому полю — управление персоналом.
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STAFF_ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    clinic: Mapped[Clinic] = relationship(back_populates="staff")
    user: Mapped[User] = relationship()
