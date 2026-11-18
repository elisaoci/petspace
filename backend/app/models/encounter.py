"""Приём в клинике и вложения к медзаписям.

`Encounter` объединяет записи одного визита (осмотр, анализы, назначения, прививки) и
фиксирует время начала и конца приёма: из этих пар потом считается метрика пилота
«время приёма». Записи приёма — обычные `MedicalRecord` с `encounter_id`, поэтому они
сразу видны владельцу в его медкарте и попадают в историю изменений.

Приём может вести врач или администратор клиники, и только при действующем доступе
клиники к питомцу. Регистратор в медданные не пишет.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.services.file_crypto import EncryptedBytes

ENCOUNTER_IN_PROGRESS = "in_progress"
ENCOUNTER_COMPLETED = "completed"
ENCOUNTER_STATUSES = (ENCOUNTER_IN_PROGRESS, ENCOUNTER_COMPLETED)


class Encounter(Base):
    __tablename__ = "encounters"
    __table_args__ = (
        # Не больше одного незавершённого приёма на пару «клиника + питомец»: защита от двойного
        # старта при гонке запросов, на уровне базы, а не только проверкой в коде.
        Index(
            "uq_encounters_one_open_per_pet",
            "clinic_id",
            "pet_id",
            unique=True,
            postgresql_where=text("status = 'in_progress'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id", ondelete="CASCADE"), index=True, nullable=False)
    pet_id: Mapped[int] = mapped_column(ForeignKey("pets.id", ondelete="CASCADE"), index=True, nullable=False)
    doctor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default=ENCOUNTER_IN_PROGRESS)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def duration_seconds(self) -> int | None:
        """Длительность завершённого приёма. У незавершённого её нет."""
        if self.finished_at is None:
            return None
        return max(0, int((self.finished_at - self.started_at).total_seconds()))


class RecordAttachment(Base):
    """Файл к медзаписи: результат анализа, снимок, заключение. Хранится зашифрованным."""

    __tablename__ = "record_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("medical_records.id", ondelete="CASCADE"), index=True, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    # deferred: в списках вложений тело файла не загружается и не расшифровывается.
    content: Mapped[bytes] = mapped_column(EncryptedBytes, nullable=False, deferred=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
