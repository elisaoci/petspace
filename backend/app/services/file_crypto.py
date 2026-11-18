"""Шифрование файлов (вложений к медзаписям) на уровне приложения: AES-256-GCM.

Тот же ключ и та же схема, что у `EncryptedText`, только для байтов. Вложения — результаты
анализов, снимки, заключения, то есть медицинские данные, и открытыми в базе лежать не должны.

Формат хранения: `b"enc:v1:" + nonce(12 байт) + шифртекст`. Префикс отличает зашифрованное
значение от возможных незашифрованных и закладывает версию схемы на будущую ротацию ключа.
"""

import os
from typing import Any

from sqlalchemy import LargeBinary
from sqlalchemy.types import TypeDecorator

from app.services.crypto import NONCE_BYTES, _aead, encryption_key

MAGIC = b"enc:v1:"


def encrypt_bytes(value: bytes, key: bytes | None = None) -> bytes:
    aesgcm = _aead()
    nonce = os.urandom(NONCE_BYTES)
    return MAGIC + nonce + aesgcm(key or encryption_key()).encrypt(nonce, value, None)


def decrypt_bytes(value: bytes, key: bytes | None = None) -> bytes:
    raw = bytes(value)
    if not raw.startswith(MAGIC):
        # Значение сохранено до включения шифрования: читаем как есть.
        return raw
    body = raw[len(MAGIC) :]
    nonce, ciphertext = body[:NONCE_BYTES], body[NONCE_BYTES:]
    return _aead()(key or encryption_key()).decrypt(nonce, ciphertext, None)


class EncryptedBytes(TypeDecorator):
    """Прозрачное шифрование бинарного поля: в БД шифртекст, в приложении — исходные байты."""

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: bytes | None, dialect: Any) -> bytes | None:
        if value is None:
            return None
        return encrypt_bytes(value)

    def process_result_value(self, value: bytes | None, dialect: Any) -> bytes | None:
        if value is None:
            return None
        return decrypt_bytes(value)
