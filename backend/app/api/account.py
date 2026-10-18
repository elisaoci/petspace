"""Удаление аккаунта владельца по 152-ФЗ.

Удаляем пользователя и каскадом всё, что к нему привязано: питомцев, медзаписи с историей,
события календаря, переписку с ИИ, доступы, согласия и refresh-токены. Запись о самом факте
удаления остаётся в аудите, но без персональных данных.
"""

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, DbSession
from app.services.audit import record_audit
from app.services.passwords import verify_password

router = APIRouter(prefix="/account", tags=["account"])


class AccountDeletePayload(BaseModel):
    # Явное подтверждение защищает от случайного удаления.
    confirm: bool = False
    # Если пароль задан — требуется; аккаунты без пароля подтверждают только флагом.
    password: str | None = None


@router.post("/delete", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    payload: AccountDeletePayload, request: Request, user: CurrentUser, db: DbSession
) -> Response:
    if not payload.confirm:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "confirmation_required", "message": "Подтвердите удаление аккаунта"},
        )

    if user.password_hash is not None and not verify_password(payload.password or "", user.password_hash):
        record_audit(
            db,
            action="account.delete.rejected",
            actor_user_id=user.id,
            entity="user",
            entity_id=user.id,
            request=request,
            details={"reason": "wrong_password"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "wrong_password", "message": "Пароль неверен"},
        )

    user_id = user.id
    # Аудит до удаления: внешний ключ actor_user_id обнулится каскадом (SET NULL),
    # поэтому в журнале остаётся факт удаления без привязки к человеку.
    record_audit(
        db,
        action="account.deleted",
        actor_user_id=user_id,
        entity="user",
        entity_id=user_id,
        request=request,
        details={"reason": "user_request"},
    )

    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
