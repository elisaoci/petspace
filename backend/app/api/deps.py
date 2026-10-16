"""Зависимости FastAPI: текущий пользователь, проверка согласий, доступ к питомцу."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import STATUS_ACTIVE, Pet, User
from app.services.consents import missing_required_consents
from app.services.security import TokenError, decode_access_token

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access-токен")

DbSession = Annotated[Session, Depends(get_db)]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: DbSession,
) -> User:
    if credentials is None or not credentials.credentials:
        raise _unauthorized("Нужна авторизация")

    try:
        user_id = decode_access_token(credentials.credentials, get_settings())
    except TokenError as exc:
        raise _unauthorized("Токен недействителен или истёк") from exc

    user = db.get(User, user_id)
    if user is None or user.status != STATUS_ACTIVE:
        raise _unauthorized("Пользователь не найден или заблокирован")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_consents(*kinds: str) -> Callable[[CurrentUser, DbSession], User]:
    """Фабрика зависимостей: эндпоинт доступен только при принятых согласиях."""

    def dependency(user: CurrentUser, db: DbSession) -> User:
        missing = missing_required_consents(db, user.id)
        outstanding = [kind for kind in kinds if kind in missing]
        if outstanding:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "consent_required",
                    "kinds": outstanding,
                    "message": "Нужно принять актуальные согласия",
                },
            )
        return user

    return dependency


def get_owned_pet(pet_id: int, user: User, db: Session) -> Pet:
    """Питомец доступен только владельцу.

    Отдаём 404, а не 403: так нельзя выяснить, существует ли чужой питомец.
    """
    pet = db.scalar(select(Pet).where(Pet.id == pet_id, Pet.owner_id == user.id))
    if pet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pet not found")
    return pet
