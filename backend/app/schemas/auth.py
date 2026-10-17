"""Схемы авторизации владельца: вход по коду, токены, согласия."""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if not EMAIL_PATTERN.match(email):
        raise ValueError("Некорректный email")
    return email


class EmailPayload(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        return normalize_email(value)


class OtpRequestPayload(EmailPayload):
    pass


class OtpRequestResponse(BaseModel):
    message: str
    expires_in: int
    # Код возвращается только вне prod: пока не подключён почтовый провайдер,
    # иначе войти в демо-стенд невозможно.
    dev_code: str | None = None


class ConsentPayload(BaseModel):
    kind: Literal["terms", "privacy", "ai_disclaimer"]
    version: str = Field(min_length=4, max_length=32)


class ConsentRequirement(BaseModel):
    kind: str
    version: str


class ConsentsPayload(BaseModel):
    consents: list[ConsentPayload] = Field(min_length=1)


class OtpVerifyPayload(EmailPayload):
    code: str = Field(min_length=4, max_length=8)


class RegisterPayload(EmailPayload):
    password: str = Field(min_length=8, max_length=128)
    # Проверяем согласия в роутере, чтобы вернуть единый формат ошибки consent_required.
    consents: list[ConsentPayload] = Field(default_factory=list)

    @field_validator("password")
    @classmethod
    def _validate_password(cls, value: str) -> str:
        if value.strip() != value:
            raise ValueError("Пароль не должен начинаться или заканчиваться пробелом")
        if len(set(value)) < 3:
            raise ValueError("Слишком простой пароль")
        return value


class LoginPayload(EmailPayload):
    password: str = Field(min_length=1, max_length=128)


class RefreshPayload(BaseModel):
    refresh_token: str = Field(min_length=16)


class UserResponse(BaseModel):
    id: int
    email: str | None
    phone: str | None
    role: str
    status: str
    consents_accepted: bool
    has_password: bool
    created_at: datetime


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class MessageResponse(BaseModel):
    message: str
