from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.pets import router as pets_router
from app.api.events import router as events_router
from app.api.chat import router as chat_router
from app.api.payments import router as payments_router
from app.config import get_settings

from app.api.health import router as health_router

app = FastAPI(
    title="PetSpace API",
    description="API единой цифровой экосистемы для владельцев домашних животных.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router, prefix="/api")
app.include_router(pets_router, prefix="/api")
app.include_router(events_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(payments_router, prefix="/api")
app.mount("/uploads", StaticFiles(directory=get_settings().upload_dir, check_dir=False), name="uploads")
