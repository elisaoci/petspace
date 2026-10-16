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
    consents: list[ConsentPayload] = Field(default_factory=list)


class RefreshPayload(BaseModel):
    refresh_token: str = Field(min_length=16)


class UserResponse(BaseModel):
    id: int
    email: str | None
    phone: str | None
    role: str
    status: str
    consents_accepted: bool
    created_at: datetime


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class MessageResponse(BaseModel):
    message: str
