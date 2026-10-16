"""Отправка писем.

Пока в проекте нет почтового провайдера, код входа печатается в лог backend
(`docker compose -p petspace logs -f backend`). Интерфейс одинаковый для обоих
вариантов, поэтому подключение провайдера не затронет бизнес-логику.
"""

import logging
from typing import Protocol

from app.config import Settings, get_settings

logger = logging.getLogger("petspace.email")


class EmailSender(Protocol):
    def send(self, to: str, subject: str, text: str) -> None: ...


class ConsoleEmailSender:
    """Пишет письмо в лог. Уровень WARNING, чтобы сообщение было видно без настройки логирования."""

    def send(self, to: str, subject: str, text: str) -> None:
        logger.warning("Письмо для %s: %s\n%s", to, subject, text)


def build_email_sender(settings: Settings) -> EmailSender:
    if settings.email_sender == "console":
        return ConsoleEmailSender()
    raise ValueError(f"Неизвестный отправитель писем: {settings.email_sender}")


def get_email_sender() -> EmailSender:
    return build_email_sender(get_settings())


def build_otp_message(code: str, ttl_minutes: int) -> tuple[str, str]:
    subject = "Код входа в PetSpace"
    text = (
        f"Ваш код входа: {code}\n"
        f"Код действует {ttl_minutes} мин. Никому его не сообщайте: сотрудники PetSpace "
        "никогда не спрашивают код."
    )
    return subject, text
