"""Схемы Smart-ID: медзаписи и доступы по ссылке."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RecordKind = Literal["visit", "vaccination", "lab", "prescription", "other"]
AccessScope = Literal["profile", "records", "vaccinations"]


class RecordCreate(BaseModel):
    kind: RecordKind = "visit"
    title: str = Field(min_length=1, max_length=200)
    occurred_at: datetime
    clinic_name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=8000)
    diagnosis: str | None = Field(default=None, max_length=4000)


class RecordUpdate(BaseModel):
    kind: RecordKind | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    occurred_at: datetime | None = None
    clinic_name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=8000)
    diagnosis: str | None = Field(default=None, max_length=4000)


class RecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pet_id: int
    kind: str
    title: str
    occurred_at: datetime
    clinic_name: str | None
    author_type: str
    source: str
    description: str | None
    diagnosis: str | None
    created_at: datetime
    updated_at: datetime


class RecordRevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    record_id: int
    action: str
    changed_by_id: int | None
    created_at: datetime


class AccessGrantCreate(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    scopes: list[AccessScope] = Field(default_factory=lambda: ["profile", "records", "vaccinations"])
    ttl_days: int = Field(default=7, ge=1, le=365)


class AccessGrantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pet_id: int
    label: str
    scopes: list[str]
    expires_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class AccessGrantCreated(AccessGrantResponse):
    """Токен возвращается только в ответе на создание доступа."""

    token: str
    url: str


# --- Публичный ответ по ссылке ---------------------------------------------


class PublicPetProfile(BaseModel):
    id: int
    name: str
    species: str
    breed: str | None
    sex: str | None
    birth_date: date | None
    weight_kg: float | None
    height_cm: float | None
    photo_url: str | None
    age_years: int | None


class PublicRecord(BaseModel):
    id: int
    kind: str
    title: str
    occurred_at: datetime
    clinic_name: str | None
    author_type: str
    description: str | None
    diagnosis: str | None


class PublicAccessGrant(BaseModel):
    label: str
    scopes: list[str]
    expires_at: datetime


class PublicAccessResponse(BaseModel):
    """Данные по ссылке. Заметки владельца и служебные поля сюда не попадают."""

    grant: PublicAccessGrant
    pet: PublicPetProfile | None = None
    records: list[PublicRecord] | None = None
    vaccinations: list[PublicRecord] | None = None
