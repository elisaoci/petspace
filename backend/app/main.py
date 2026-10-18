from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.access import router as access_router
from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.errors import install_error_handlers
from app.api.events import router as events_router
from app.api.health import router as health_router
from app.api.payments import router as payments_router
from app.api.pets import router as pets_router
from app.api.records import router as records_router
from app.config import get_settings

API_V1_PREFIX = "/api/v1"

app = FastAPI(
    title="PetSpace API",
    description=(
        "API единой цифровой экосистемы для владельцев домашних животных.\n\n"
        f"Рабочая версия API: `{API_V1_PREFIX}`. Авторизация — JWT: получите код "
        "(`POST /api/v1/auth/otp/request`), обменяйте его на токены "
        "(`POST /api/v1/auth/otp/verify`) и передавайте access-токен в заголовке "
        "`Authorization: Bearer <token>`.\n\n"
        "Ошибки приходят в едином формате: `{\"error\": {\"code\", \"message\", \"details\"}}`.\n"
        "Списки поддерживают `limit`/`offset` и заголовок `X-Total-Count`.\n"
        "Повторные записи защищены заголовком `Idempotency-Key`."
    ),
    version="0.1.0",
    openapi_url=f"{API_V1_PREFIX}/openapi.json",
    docs_url="/docs",
    redoc_url=None,
)

install_error_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health без версии: его дёргает инфраструктура (балансировщик, мониторинг).
app.include_router(health_router, prefix="/api")
app.include_router(health_router, prefix=API_V1_PREFIX)

for router in (
    auth_router,
    pets_router,
    events_router,
    records_router,
    access_router,
    chat_router,
    payments_router,
    admin_router,
):
    app.include_router(router, prefix=API_V1_PREFIX)

app.mount("/uploads", StaticFiles(directory=get_settings().upload_dir, check_dir=False), name="uploads")
