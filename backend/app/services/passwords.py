"""Хэширование паролей.

Используется PBKDF2-HMAC-SHA256 из стандартной библиотеки: параметры (алгоритм,
число итераций, соль) хранятся в самом хэше, поэтому переход на Argon2id позже
не потребует сброса паролей — достаточно проверять префикс алгоритма.
"""

import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 600_000
SALT_BYTES = 16


def hash_password(password: str, iterations: int = DEFAULT_ITERATIONS) -> str:
    salt = secrets.token_hex(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations)
    return f"{ALGORITHM}${iterations}${salt}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algorithm, iterations, salt, expected = stored.split("$")
        rounds = int(iterations)
    except (AttributeError, ValueError):
        return False
    if algorithm != ALGORITHM or rounds <= 0:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), rounds)
    return hmac.compare_digest(digest.hex(), expected)
