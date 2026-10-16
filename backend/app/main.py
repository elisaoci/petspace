from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.events import router as events_router
from app.api.health import router as health_router
from app.api.payments import router as payments_router
from app.api.pets import router as pets_router
from app.config import get_settings

API_V1_PREFIX = "/api/v1"

app = FastAPI(
    title="PetSpace API",
    description=(
        "API единой цифровой экосистемы для владельцев домашних животных.\n\n"
        f"Рабочая версия API: `{API_V1_PREFIX}`. Авторизация — JWT: получите код "
        "(`POST /api/v1/auth/otp/request`), обменяйте его на токены "
        "(`POST /api/v1/auth/otp/verify`) и передавайте access-токен в заголовке "
        "`Authorization: Bearer <token>`."
    ),
    version="0.1.0",
    openapi_url=f"{API_V1_PREFIX}/openapi.json",
    docs_url="/docs",
    redoc_url=None,
)

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

for router in (auth_router, pets_router, events_router, chat_router, payments_router):
    app.include_router(router, prefix=API_V1_PREFIX)

app.mount("/uploads", StaticFiles(directory=get_settings().upload_dir, check_dir=False), name="uploads")
