"""Схемы клиник: заявка организации, профиль, сотрудники, модерация."""

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.schemas.auth import ConsentPayload, TokenPairResponse, normalize_email
from app.services.passwords import password_error

# Строки приходят «как есть» из формы: убираем пробелы по краям до проверки длины.
Name200 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]
Address300 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=300)]
PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=1000)]

StaffRole = Literal["clinic_admin", "clinic_doctor", "clinic_registrar"]
StaffStatusValue = Literal["active", "disabled"]

_INN10_WEIGHTS = (2, 4, 10, 3, 5, 9, 4, 6, 8)
_INN12_WEIGHTS_11 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_INN12_WEIGHTS_12 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)


def _inn_digit(digits: list[int], weights: tuple[int, ...]) -> int:
    return sum(w * d for w, d in zip(weights, digits, strict=False)) % 11 % 10


def validate_inn(value: str) -> str:
    """ИНН юрлица (10 цифр) или ИП (12 цифр) с проверкой контрольных цифр."""
    inn = value.strip()
    if not inn.isdigit() or len(inn) not in (10, 12):
        raise ValueError("ИНН должен состоять из 10 или 12 цифр")
    digits = [int(char) for char in inn]
    if len(inn) == 10:
        valid = _inn_digit(digits, _INN10_WEIGHTS) == digits[9]
    else:
        valid = (
            _inn_digit(digits, _INN12_WEIGHTS_11) == digits[10]
            and _inn_digit(digits, _INN12_WEIGHTS_12) == digits[11]
        )
    if not valid:
        raise ValueError("Некорректный ИНН: не сходится контрольная цифра")
    return inn


def normalize_phone(value: str) -> str:
    """Приводит телефон к виду +7XXXXXXXXXX (российские номера) или +<цифры> (международные)."""
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    if len(digits) == 10:
        return "+7" + digits
    if value.strip().startswith("+") and 10 <= len(digits) <= 15:
        return "+" + digits
    raise ValueError("Некорректный телефон")


class _ClinicFields(BaseModel):
    """Общие проверки полей, чтобы заявка и редактирование не расходились."""

    @field_validator("inn", check_fields=False)
    @classmethod
    def _check_inn(cls, value: str | None) -> str | None:
        return None if value is None else validate_inn(value)

    @field_validator("phone", check_fields=False)
    @classmethod
    def _check_phone(cls, value: str | None) -> str | None:
        return None if value is None else normalize_phone(value)

    @field_validator("email", check_fields=False)
    @classmethod
    def _check_clinic_email(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return normalize_email(value)


class ClinicRegisterPayload(_ClinicFields):
    """Заявка организации. Вместе с ней создаётся аккаунт администратора клиники."""

    clinic_name: Name200
    inn: str
    address: Address300
    phone: str
    # Публичная почта клиники (необязательно). Логин администратора — admin_email.
    email: str | None = None
    contact_name: PersonName
    admin_email: str
    password: str = Field(min_length=8, max_length=128)
    consents: list[ConsentPayload] = Field(default_factory=list)

    @field_validator("admin_email")
    @classmethod
    def _check_admin_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        problem = password_error(value)
        if problem:
            raise ValueError(problem)
        return value


class ClinicUpdatePayload(_ClinicFields):
    name: Name200 | None = None
    inn: str | None = None
    address: Address300 | None = None
    phone: str | None = None
    email: str | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> "ClinicUpdatePayload":
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно поле для изменения")
        return self


class ClinicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    inn: str
    address: str
    phone: str
    email: str | None
    status: str
    status_reason: str | None
    moderated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ClinicMeResponse(ClinicResponse):
    """Клиника глазами её сотрудника: добавляется его роль."""

    my_staff_id: int
    my_role: str
    my_full_name: str


class ClinicRegisterResponse(TokenPairResponse):
    clinic: ClinicResponse


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class StaffResponse(BaseModel):
    id: int
    user_id: int
    email: str | None
    full_name: str
    role: str
    status: str
    created_at: datetime


class StaffInvitePayload(BaseModel):
    email: str
    full_name: PersonName
    role: StaffRole

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        return normalize_email(value)


class StaffUpdatePayload(BaseModel):
    full_name: PersonName | None = None
    role: StaffRole | None = None
    status: StaffStatusValue | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> "StaffUpdatePayload":
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно поле для изменения")
        return self


class ModerationReasonPayload(BaseModel):
    reason: Reason


class AdminClinicListItem(ClinicResponse):
    staff_count: int
    documents_count: int


class AdminClinicDetail(ClinicResponse):
    created_by_email: str | None
    moderated_by_email: str | None
    staff: list[StaffResponse]
    documents: list[DocumentResponse]
