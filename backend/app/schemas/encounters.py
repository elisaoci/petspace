"""Схемы приёма: запись врача, правка, вложения, приём с записями."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.medical import RecordKind
from app.schemas.patient_access import PatientBrief

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class ClinicRecordCreate(BaseModel):
    """Запись врача внутри приёма.

    Название клиники и автор берутся с сервера, из аккаунта сотрудника, а не из запроса.
    """

    kind: RecordKind = "visit"
    title: Title
    description: str | None = Field(default=None, max_length=8000)
    diagnosis: str | None = Field(default=None, max_length=4000)
    # По умолчанию — момент создания записи. Будущее время (больше 5 минут) не принимается.
    occurred_at: datetime | None = None


class ClinicRecordUpdate(BaseModel):
    """Правка своей записи. Вид записи менять нельзя: от него зависят права доступа."""

    title: Title | None = None
    description: str | None = Field(default=None, max_length=8000)
    diagnosis: str | None = Field(default=None, max_length=4000)
    occurred_at: datetime | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> "ClinicRecordUpdate":
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно поле для изменения")
        return self


class AttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    record_id: int
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class ClinicRecordResponse(BaseModel):
    id: int
    pet_id: int
    encounter_id: int | None
    kind: str
    title: str
    occurred_at: datetime
    description: str | None
    diagnosis: str | None
    clinic_name: str | None
    author_type: str
    author_name: str | None
    created_at: datetime
    updated_at: datetime
    attachments: list[AttachmentResponse] = Field(default_factory=list)


class EncounterResponse(BaseModel):
    id: int
    pet: PatientBrief
    status: str
    doctor_name: str | None
    started_at: datetime
    finished_at: datetime | None
    # Длительность завершённого приёма в секундах: из неё считается метрика пилота.
    duration_seconds: int | None
    records_count: int


class EncounterDetail(EncounterResponse):
    records: list[ClinicRecordResponse]
