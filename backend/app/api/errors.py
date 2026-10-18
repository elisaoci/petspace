"""Единый формат ошибок API.

Любой ответ с ошибкой выглядит так:

    {
      "error": {"code": "not_found", "message": "Pet not found", "details": {...}},
      "detail": "Pet not found"    # legacy-поле, оставлено для совместимости клиентов
    }

`code` — машинный идентификатор (не меняется), `message` — текст для человека,
`details` — дополнительный контекст (список ошибок валидации, какие согласия нужны и т.п.).
"""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.utils import is_body_allowed_for_status_code
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("petspace.errors")

STATUS_CODES = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthorized",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "validation_error",
    status.HTTP_429_TOO_MANY_REQUESTS: "too_many_requests",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "internal_error",
    status.HTTP_503_SERVICE_UNAVAILABLE: "service_unavailable",
}

DEFAULT_MESSAGES = {
    "bad_request": "Некорректный запрос",
    "unauthorized": "Нужна авторизация",
    "forbidden": "Недостаточно прав",
    "not_found": "Не найдено",
    "conflict": "Конфликт данных",
    "validation_error": "Проверьте данные запроса",
    "too_many_requests": "Слишком много запросов",
    "internal_error": "Внутренняя ошибка сервера",
    "service_unavailable": "Сервис временно недоступен",
}


def error_payload(
    code: str,
    message: str,
    *,
    details: Any | None = None,
    legacy_detail: Any | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    # legacy: старые клиенты читают detail. Убирать, когда все перейдут на error.
    payload["detail"] = legacy_detail if legacy_detail is not None else message
    return payload


def error_from_http_exception(exc: StarletteHTTPException) -> JSONResponse:
    code = STATUS_CODES.get(exc.status_code, "error")
    message = DEFAULT_MESSAGES.get(code, "Ошибка")
    details: Any | None = None
    detail = exc.detail

    if isinstance(detail, dict):
        # Наши доменные ошибки: {"error": "consent_required", "message": "...", ...}
        domain_code = detail.get("error")
        if isinstance(domain_code, str):
            code = domain_code
        message = detail.get("message") or message
        details = {key: value for key, value in detail.items() if key not in {"error", "message"}} or None
    elif isinstance(detail, str):
        message = detail

    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder(error_payload(code, message, details=details, legacy_detail=detail)),
        headers=exc.headers,
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if not is_body_allowed_for_status_code(exc.status_code):
            return JSONResponse(status_code=exc.status_code, content=None, headers=exc.headers)
        return error_from_http_exception(exc)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = jsonable_encoder(exc.errors())
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_payload(
                "validation_error",
                DEFAULT_MESSAGES["validation_error"],
                details=errors,
                legacy_detail=errors,
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Необработанная ошибка на %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_payload("internal_error", DEFAULT_MESSAGES["internal_error"]),
        )
