"""Правила записи врача: какие разделы нужны для какого вида записи, вложения, время.

Запись в карту разрешена в пределах разделов, которые владелец открыл клинике:

- прививка — раздел `vaccinations` или `records`;
- осмотр, анализы, назначения и прочее — раздел `records`.

Так владелец управляет не только чтением, но и записью: открыв клинике только профиль,
он не даёт ни читать историю, ни писать в неё.
"""

from datetime import timedelta

from app.models import RECORD_VACCINATION, SCOPE_RECORDS, SCOPE_VACCINATIONS

MAX_ATTACHMENTS_PER_RECORD = 10
# Допуск на расхождение часов: запись «из будущего» дальше этого срока отклоняется.
MAX_FUTURE_SKEW = timedelta(minutes=5)


def scopes_for_kind(kind: str) -> tuple[str, ...]:
    """Разделы доступа, любого из которых достаточно для записи такого вида."""
    if kind == RECORD_VACCINATION:
        return (SCOPE_RECORDS, SCOPE_VACCINATIONS)
    return (SCOPE_RECORDS,)


def grant_allows_kind(grant_scopes: list[str], kind: str) -> bool:
    return any(scope in grant_scopes for scope in scopes_for_kind(kind))
