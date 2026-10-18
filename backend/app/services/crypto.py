"""Шифрование чувствительных текстов на уровне приложения (AES-256-GCM).

Зачем: заметки владельца (аллергии, хронические болезни) — медицинские данные, им нельзя
лежать в базе открытым текстом. AES-256-GCM даёт и конфиденциальность, и защиту от подмены.

Формат хранения: `enc:v1:<base64(nonce || ciphertext)>`. Префикс нужен, чтобы:
- отличать зашифрованные значения от старых записей, сохранённых до включения шифрования;
- понимать версию схемы при будущей ротации ключа.

Ключ (32 байта):
- prod: обязателен `MEDICAL_ENCRYPTION_KEY` (base64), задаётся в секрет-хранилище;
- dev: выводится из `JWT_SECRET`, чтобы локальный запуск работал без настройки.
  Это компромисс только для разработки: в prod такой вывод запрещён.
"""

import base64
import hashlib
import os
from typing import Any

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.config import Settings, get_settings

PREFIX = "enc:v1:"
NONCE_BYTES = 12
KEY_BYTES = 32
DEV_DERIVATION_SALT = b"petspace-medical-dev"


class EncryptionUnavailable(RuntimeError):
    """Пакет cryptography не установлен: шифрование невозможно."""


def _aead() -> Any:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:  # pragma: no cover - зависит от окружения
        raise EncryptionUnavailable(
            "Для шифрования нужен пакет cryptography. Пересоберите образ backend: "
            "docker compose -p petspace up -d --build"
        ) from exc
    return AESGCM


def encryption_key(settings: Settings | None = None) -> bytes:
    settings = settings or get_settings()
    if settings.medical_encryption_key:
        raw = base64.b64decode(settings.medical_encryption_key)
        if len(raw) != KEY_BYTES:
            raise ValueError("MEDICAL_ENCRYPTION_KEY должен быть 32 байта в base64")
        return raw
    if settings.is_production:
        raise ValueError("MEDICAL_ENCRYPTION_KEY обязателен в prod")
    # Только для локальной разработки.
    return hashlib.sha256(DEV_DERIVATION_SALT + settings.jwt_secret.encode()).digest()


def encrypt_text(value: str, key: bytes | None = None) -> str:
    if value is None:  # pragma: no cover - защита от неаккуратного вызова
        return value
    aesgcm = _aead()
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = aesgcm(key or encryption_key()).encrypt(nonce, value.encode(), None)
    return PREFIX + base64.b64encode(nonce + ciphertext).decode()


def decrypt_text(value: str, key: bytes | None = None) -> str:
    if value is None:  # pragma: no cover
        return value
    if not value.startswith(PREFIX):
        # Значение сохранено до включения шифрования — читаем как есть.
        return value
    aesgcm = _aead()
    raw = base64.b64decode(value[len(PREFIX):])
    nonce, ciphertext = raw[:NONCE_BYTES], raw[NONCE_BYTES:]
    return aesgcm(key or encryption_key()).decrypt(nonce, ciphertext, None).decode()


def is_encrypted(value: str | None) -> bool:
    return bool(value and value.startswith(PREFIX))


class EncryptedText(TypeDecorator):
    """Прозрачное шифрование текстового поля: в БД шифртекст, в приложении — открытый текст."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:
        if value is None:
            return None
        return encrypt_text(value)

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:
        if value is None:
            return None
        return decrypt_text(value)
