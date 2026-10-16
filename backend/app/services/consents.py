"""Согласия пользователя: запись и проверка актуальности версий (152-ФЗ)."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CONSENT_VERSIONS, REQUIRED_CONSENTS, Consent


def accepted_consents(db: Session, user_id: int) -> set[tuple[str, str]]:
    rows = db.execute(select(Consent.kind, Consent.version).where(Consent.user_id == user_id)).all()
    return {(kind, version) for kind, version in rows}


def missing_required_consents(db: Session, user_id: int) -> list[str]:
    """Виды согласий, которые не приняты в актуальной версии."""
    accepted = accepted_consents(db, user_id)
    return [kind for kind in REQUIRED_CONSENTS if (kind, CONSENT_VERSIONS[kind]) not in accepted]


def validate_consents(consents: Iterable[tuple[str, str]]) -> list[str]:
    """Возвращает список проблем: неизвестный вид согласия или устаревшая версия текста."""
    problems: list[str] = []
    for kind, version in consents:
        expected = CONSENT_VERSIONS.get(kind)
        if expected is None:
            problems.append(f"Неизвестный вид согласия: {kind}")
        elif expected != version:
            problems.append(f"Версия согласия «{kind}» устарела: ожидается {expected}")
    return problems


def record_consents(
    db: Session, user_id: int, consents: Iterable[tuple[str, str]], ip: str | None
) -> None:
    existing = accepted_consents(db, user_id)
    for kind, version in consents:
        if (kind, version) in existing:
            continue
        db.add(Consent(user_id=user_id, kind=kind, version=version, ip=ip))
