"""Идемпотентность записи: один ключ — один результат.

Заголовок `Idempotency-Key` опционален. Если он есть:
- повтор с тем же ключом и тем же телом возвращает сохранённый ответ и заголовок
  `Idempotent-Replay: true` — клиент не создаёт дубль при ретрае;
- повтор с тем же ключом, но другим телом — ошибка 409 `idempotency_conflict`;
- ключи живут 24 часа, затем освобождаются.
"""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import IdempotencyKey

IDEMPOTENCY_HEADER = "Idempotency-Key"
TTL = timedelta(hours=24)


def _payload_hash(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def replay_response(
    db: Session,
    *,
    user_id: int,
    key: str,
    endpoint: str,
    payload: Any,
) -> JSONResponse | None:
    """Возвращает сохранённый ответ, если такой ключ уже использован."""
    stored = db.scalar(
        select(IdempotencyKey).where(
            IdempotencyKey.user_id == user_id,
            IdempotencyKey.key == key,
            IdempotencyKey.endpoint == endpoint,
        )
    )
    if stored is None:
        return None

    if stored.expires_at <= datetime.now(UTC):
        db.delete(stored)
        db.commit()
        return None

    if not hmac.compare_digest(stored.request_hash, _payload_hash(payload)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "idempotency_conflict",
                "message": "Этот Idempotency-Key уже использован с другими данными",
            },
        )

    return JSONResponse(
        status_code=stored.response_status,
        content=stored.response_body,
        headers={"Idempotent-Replay": "true"},
    )


def store_response(
    db: Session,
    *,
    user_id: int,
    key: str,
    endpoint: str,
    payload: Any,
    status_code: int,
    body: dict[str, Any],
) -> None:
    """Сохраняет ответ, чтобы повтор запроса не создал дубль."""
    db.add(
        IdempotencyKey(
            user_id=user_id,
            key=key[:255],
            endpoint=endpoint,
            request_hash=_payload_hash(payload),
            response_status=status_code,
            response_body=body,
            expires_at=datetime.now(UTC) + TTL,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        # Параллельный запрос с тем же ключом уже сохранил ответ — это не ошибка.
        db.rollback()
