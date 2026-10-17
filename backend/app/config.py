from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_JWT_SECRET = "dev-insecure-change-me"


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://petspace:petspace@localhost:5432/petspace"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    upload_dir: str = "uploads"

    # dev | staging | prod. В prod запрещены небезопасные значения по умолчанию.
    environment: str = "dev"

    jwt_secret: str = INSECURE_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    otp_ttl_minutes: int = 5
    otp_max_attempts: int = 5
    otp_max_requests_per_hour: int = 3

    # Стоимость PBKDF2 и защита от подбора пароля.
    password_iterations: int = 600_000
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15

    # console — код печатается в логи backend, smtp — реальная отправка (подключим позже).
    email_sender: str = "console"
    email_from: str = "PetSpace <no-reply@petspace.local>"

    # Только для локальной разработки: возвращать код входа в ответе API,
    # чтобы демо работало без почтового провайдера. В prod запрещено валидатором.
    expose_dev_otp: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def _check_production_secrets(self) -> "Settings":
        if self.environment == "prod":
            if self.jwt_secret == INSECURE_JWT_SECRET:
                raise ValueError("JWT_SECRET обязателен в prod: задайте случайное значение")
            if len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET в prod должен быть не короче 32 символов")
            if self.expose_dev_otp:
                raise ValueError("EXPOSE_DEV_OTP недопустим в prod: код входа нельзя отдавать в ответе")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()
