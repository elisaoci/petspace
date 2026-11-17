"""Бизнес-логика доступа клиники к пациенту: коды, выдача доступа, лимиты.

Здесь только то, что не зависит от HTTP: генерация и проверка кода, создание или
продление `AccessGrant` для клиники, подсчёт попыток для защиты от перебора.
"""

import secrets
from datetime import datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    ACCESS_SCOPES,
    REQUEST_EXPIRED,
    REQUEST_PENDING,
    ROLE_CLINIC_REGISTRAR,
    SCOPE_PROFILE,
    AccessGrant,
    AccessRequest,
    AuditLog,
    Clinic,
    ClinicStaff,
)
from app.services.security import hash_otp

# Алфавит без символов, которые путают на слух и на глаз: 0/O, 1/I/L.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8
CODE_TTL_MINUTES = 15

REQUEST_TTL_HOURS = 72

# Защита от перебора: 31^8 ≈ 8.5·10^11 комбинаций, код живёт 15 минут, а число неудачных
# попыток клиники в час ограничено. Запросов по телефону — не больше суток-лимита на клинику.
MAX_FAILED_CODE_ATTEMPTS_PER_HOUR = 20
MAX_REQUESTS_PER_DAY = 50

# Что видит сотрудник по роли внутри выданных клинике разделов. Регистратору диагнозы
# и история болезни не нужны: он видит только профиль питомца.
ROLE_ALLOWED_SCOPES: dict[str, tuple[str, ...]] = {
    ROLE_CLINIC_REGISTRAR: (SCOPE_PROFILE,),
}


# --- Коды ---------------------------------------------------------------------------


def generate_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def format_code(code: str) -> str:
    """ABCDEFGH → ABCD-EFGH: так код проще продиктовать."""
    return f"{code[:4]}-{code[4:]}"


def normalize_code(raw: str) -> str | None:
    """Приводит введённый код к каноническому виду. None — формат заведомо неверный."""
    code = "".join(char for char in raw.upper() if not char.isspace() and char != "-")
    if len(code) != CODE_LENGTH or any(char not in CODE_ALPHABET for char in code):
        return None
    return code


def hash_code(code: str) -> str:
    """HMAC с секретом приложения: утечка таблицы не позволяет перебирать коды офлайн."""
    return hash_otp(code, get_settings().jwt_secret)


# --- Выдача доступа клинике -----------------------------------------------------------


def ordered_scopes(scopes: set[str] | list[str]) -> list[str]:
    """Разделы в стабильном порядке (profile, records, vaccinations) и без дублей."""
    wanted = set(scopes)
    return [scope for scope in ACCESS_SCOPES if scope in wanted]


def grant_clinic_access(
    db: Session,
    *,
    clinic: Clinic,
    pet_id: int,
    scopes: list[str],
    ttl_days: int,
    now: datetime,
) -> AccessGrant:
    """Открывает клинике доступ к питомцу или продлевает уже действующий.

    Одна клиника — один действующий доступ на питомца: владельцу достаточно одного клика
    для отзыва, а не поиска нескольких одинаковых строк. Повторная выдача объединяет разделы
    и берёт более поздний срок. Вызывающий код делает commit.
    """
    expires_at = now + timedelta(days=ttl_days)
    grant = db.scalar(
        select(AccessGrant)
        .where(
            AccessGrant.clinic_id == clinic.id,
            AccessGrant.pet_id == pet_id,
            AccessGrant.revoked_at.is_(None),
            AccessGrant.expires_at > now,
        )
        .order_by(AccessGrant.id.desc())
    )
    if grant is None:
        grant = AccessGrant(
            pet_id=pet_id,
            clinic_id=clinic.id,
            label=clinic.name,
            token_hash=None,
            scopes=ordered_scopes(scopes),
            expires_at=expires_at,
        )
        db.add(grant)
    else:
        grant.scopes = ordered_scopes(set(grant.scopes or []) | set(scopes))
        grant.expires_at = max(grant.expires_at, expires_at)
    db.flush()
    return grant


def visible_scopes(role: str, grant_scopes: list[str]) -> list[str]:
    """Пересечение выданных владельцем разделов и того, что роли сотрудника разрешено видеть."""
    allowed = ROLE_ALLOWED_SCOPES.get(role)
    if allowed is None:
        return ordered_scopes(grant_scopes)
    return ordered_scopes(set(grant_scopes) & set(allowed))


# --- Защита от перебора ---------------------------------------------------------------


def failed_code_attempts_last_hour(db: Session, clinic_id: int, now: datetime) -> int:
    """Неудачные вводы кода всеми сотрудниками клиники за последний час (по журналу аудита)."""
    staff_ids = select(ClinicStaff.user_id).where(ClinicStaff.clinic_id == clinic_id)
    return (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action == "access_code.redeem_failed",
                AuditLog.actor_user_id.in_(staff_ids),
                AuditLog.created_at > now - timedelta(hours=1),
            )
        )
        or 0
    )


def requests_last_day(db: Session, clinic_id: int, now: datetime) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(AccessRequest)
            .where(AccessRequest.clinic_id == clinic_id, AccessRequest.created_at > now - timedelta(days=1))
        )
        or 0
    )


def request_status_condition(requested: str, now: datetime):
    """SQL-условие по статусу запроса. `expired` вычисляется: это `pending` с вышедшим сроком."""
    if requested == REQUEST_PENDING:
        return and_(AccessRequest.status == REQUEST_PENDING, AccessRequest.expires_at > now)
    if requested == REQUEST_EXPIRED:
        return and_(AccessRequest.status == REQUEST_PENDING, AccessRequest.expires_at <= now)
    return AccessRequest.status == requested


# --- Представление данных ------------------------------------------------------------


def mask_phone(phone: str) -> str:
    """+74951234567 → +7*******67: сотрудник видит, что запрос ушёл, но не весь номер."""
    if len(phone) <= 4:
        return "*" * len(phone)
    return phone[:2] + "*" * (len(phone) - 4) + phone[-2:]
