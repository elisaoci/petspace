"""Бизнес-логика клиник: проверка загружаемых документов и письма сотрудникам.

Письма уходят через тот же интерфейс, что и коды входа (`get_email_sender`): пока нет
почтового провайдера, они печатаются в лог backend. Сбой отправки не должен ломать
запрос, поэтому ошибки только логируются.
"""

import logging
from urllib.parse import quote

from app.models import Clinic
from app.services.email import get_email_sender

logger = logging.getLogger("petspace.clinics")

# Названия ролей для писем и интерфейса.
ROLE_TITLES = {
    "clinic_admin": "Администратор",
    "clinic_doctor": "Врач",
    "clinic_registrar": "Регистратор",
}

MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
MAX_DOCUMENTS_PER_CLINIC = 10

# Сигнатуры файлов: расширению и заголовку Content-Type от клиента верить нельзя.
_SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    (b"%PDF-", "application/pdf", ".pdf"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
)


class DocumentError(ValueError):
    """Файл не подходит: слишком большой, пустой или неподдерживаемого типа."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def detect_document_type(data: bytes) -> tuple[str, str]:
    """Возвращает (content_type, расширение) по содержимому файла."""
    if not data:
        raise DocumentError("document_empty", "Файл пустой")
    if len(data) > MAX_DOCUMENT_BYTES:
        raise DocumentError(
            "document_too_large", f"Файл больше {MAX_DOCUMENT_BYTES // (1024 * 1024)} МБ"
        )
    for signature, content_type, extension in _SIGNATURES:
        if data.startswith(signature):
            return content_type, extension
    raise DocumentError("document_type_unsupported", "Поддерживаются только PDF, JPG и PNG")


def safe_filename(filename: str | None, extension: str) -> str:
    """Имя без путей и управляющих символов, с расширением, соответствующим содержимому."""
    base = (filename or "document").replace("\\", "/").split("/")[-1]
    base = "".join(char for char in base if char.isprintable()).strip().strip(".")
    stem = base.rsplit(".", 1)[0] if "." in base else base
    stem = stem[:120] or "document"
    return f"{stem}{extension}"


def content_disposition(filename: str) -> str:
    """Заголовок скачивания с поддержкой кириллицы в имени файла (RFC 5987)."""
    return f"attachment; filename*=UTF-8''{quote(filename)}"


def _send(to: str | None, subject: str, text: str) -> None:
    if not to:
        return
    try:
        get_email_sender().send(to, subject, text)
    except Exception:  # noqa: BLE001 - письмо вторично, запрос из-за него не падает
        logger.exception("Не удалось отправить письмо на %s", to)


def notify_application_received(to: str, clinic: Clinic) -> None:
    _send(
        to,
        "Заявка на подключение клиники принята",
        f"Заявка клиники «{clinic.name}» (ИНН {clinic.inn}) принята и ждёт проверки модератором PetSpace.\n"
        "Пока идёт проверка, вы можете войти в кабинет, загрузить документы и посмотреть статус заявки.",
    )


def notify_clinic_approved(to: str | None, clinic: Clinic) -> None:
    _send(
        to,
        "Клиника подключена к PetSpace",
        f"Клиника «{clinic.name}» прошла проверку. Теперь можно добавлять сотрудников и принимать пациентов.",
    )


def notify_clinic_rejected(to: str | None, clinic: Clinic) -> None:
    _send(
        to,
        "Заявка клиники отклонена",
        f"Заявка клиники «{clinic.name}» отклонена.\nПричина: {clinic.status_reason}\n"
        "Исправьте данные или загрузите недостающие документы и отправьте заявку на повторную проверку.",
    )


def notify_clinic_suspended(to: str | None, clinic: Clinic) -> None:
    _send(
        to,
        "Работа клиники в PetSpace приостановлена",
        f"Доступ клиники «{clinic.name}» к данным пациентов приостановлен.\nПричина: {clinic.status_reason}",
    )


def notify_staff_invited(to: str, clinic: Clinic, role_title: str) -> None:
    _send(
        to,
        f"Вас добавили в клинику «{clinic.name}»",
        f"Вас добавили в клинику «{clinic.name}» PetSpace с ролью «{role_title}».\n"
        "Чтобы задать пароль, откройте страницу входа, выберите «Забыли пароль» и введите этот адрес: "
        "на почту придёт код для установки пароля.",
    )
