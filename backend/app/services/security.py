"""Криптографические примитивы авторизации: JWT, OTP, хэши токенов."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt

from app.config import Settings

ACCESS_TOKEN_TYPE = "access"


class TokenError(Exception):
    """Токен отсутствует, просрочен, подделан или не того типа."""


def hash_token(token: str) -> str:
    """Refresh-токены и OTP хранятся в БД только в виде хэша."""
    return hashlib.sha256(token.encode()).hexdigest()


def hash_otp(code: str, secret: str) -> str:
    """6 цифр — слишком маленькое пространство для простого хэша, поэтому HMAC с секретом приложения."""
    return hmac.new(secret.encode(), code.encode(), hashlib.sha256).hexdigest()


def codes_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)


def generate_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def create_access_token(user_id: int, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_ttl_minutes)).timestamp()),
        "jti": secrets.token_urlsafe(12),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> int:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise TokenError("Недействительный токен") from exc

    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise TokenError("Неверный тип токена")

    subject = payload.get("sub")
    if not subject or not str(subject).isdigit():
        raise TokenError("В токене нет пользователя")
    return int(subject)
