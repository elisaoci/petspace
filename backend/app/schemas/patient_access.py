"""Схемы доступа клиники к пациенту: коды, запросы, список пациентов, справочник клиник."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.schemas.clinics import normalize_phone
from app.schemas.medical import AccessScope

RequestStatusFilter = Literal["pending", "approved", "denied", "expired", "cancelled"]

PetNameQuery = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
ALL_SCOPES = ["profile", "records", "vaccinations"]


def _default_scopes() -> list[str]:
    return list(ALL_SCOPES)


# --- Владелец: коды -------------------------------------------------------------------


class AccessCodeCreate(BaseModel):
    scopes: list[AccessScope] = Field(default_factory=_default_scopes, min_length=1)
    # Сколько дней клиника сможет смотреть карту после ввода кода.
    ttl_days: int = Field(default=7, ge=1, le=365)


class AccessCodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pet_id: int
    scopes: list[str]
    ttl_days: int
    expires_at: datetime
    used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class AccessCodeCreated(AccessCodeResponse):
    """Сам код возвращается только при создании: в базе его нет."""

    code: str


# --- Владелец: телефон ----------------------------------------------------------------


class PhonePayload(BaseModel):
    phone: str | None = None

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return normalize_phone(value)


class PhoneResponse(BaseModel):
    phone: str | None


# --- Владелец: входящие запросы -------------------------------------------------------


class ClinicBrief(BaseModel):
    id: int
    name: str
    address: str
    phone: str


class PetBrief(BaseModel):
    id: int
    name: str
    species: str
    photo_url: str | None


class OwnerAccessRequest(BaseModel):
    id: int
    status: str
    clinic: ClinicBrief
    pet: PetBrief
    scopes: list[str]
    ttl_days: int
    message: str | None
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None
    grant_id: int | None


class AccessRequestApprove(BaseModel):
    """Владелец может сузить запрос: меньше разделов и/или короче срок. Расширять нельзя."""

    scopes: list[AccessScope] | None = Field(default=None, min_length=1)
    ttl_days: int | None = Field(default=None, ge=1, le=365)


# --- Клиника: коды и запросы ----------------------------------------------------------


class RedeemPayload(BaseModel):
    code: str = Field(min_length=4, max_length=32)


class AccessRequestCreate(BaseModel):
    pet_name: PetNameQuery
    owner_phone: str
    scopes: list[AccessScope] = Field(default_factory=_default_scopes, min_length=1)
    ttl_days: int = Field(default=7, ge=1, le=365)
    message: str | None = Field(default=None, max_length=500)

    @field_validator("owner_phone")
    @classmethod
    def _check_phone(cls, value: str) -> str:
        return normalize_phone(value)

    @model_validator(mode="after")
    def _clean_message(self) -> "AccessRequestCreate":
        if self.message is not None:
            self.message = self.message.strip() or None
        return self


class PatientBrief(BaseModel):
    id: int
    name: str
    species: str
    breed: str | None
    photo_url: str | None


class ClinicAccessRequest(BaseModel):
    """Запрос глазами клиники.

    Пока владелец не одобрил, пациента в ответе нет: по нему нельзя понять, нашёлся ли питомец.
    """

    id: int
    status: str
    pet_name: str
    owner_phone_masked: str
    scopes: list[str]
    ttl_days: int
    message: str | None
    requested_by: str | None
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None
    patient: PatientBrief | None = None
    grant_id: int | None = None


class PatientAccessResponse(BaseModel):
    """Результат ввода кода: какой пациент открыт и на каких условиях."""

    grant_id: int
    pet: PatientBrief
    scopes: list[str]
    expires_at: datetime


class PatientListItem(BaseModel):
    pet: PatientBrief
    grant_id: int
    scopes: list[str]
    expires_at: datetime
    last_used_at: datetime | None


# --- Справочник клиник ----------------------------------------------------------------


class DirectoryClinic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    address: str
    phone: str
