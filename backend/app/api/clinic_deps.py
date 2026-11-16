"""Зависимости кабинета клиники: кто сотрудник, чья клиника, одобрена ли она.

Уровни доступа (каждый следующий включает предыдущий):

1. `ClinicMember` — активный сотрудник клиники в любом статусе клиники. Нужен, чтобы
   заявка на проверке могла загрузить документы и посмотреть статус.
2. `ApprovedClinicMember` — то же, но клиника одобрена и сотрудник принял актуальные
   согласия. Сюда добавляются все функции работы с пациентами на следующих этапах.
3. `require_clinic_roles(...)` — одобренная клиника и нужная роль внутри неё.

Все запросы к данным клиники обязаны фильтроваться по `ctx.clinic.id`: чужой объект
отдаётся как 404, как и в остальном API.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import CLINIC_APPROVED, STAFF_ACTIVE, Clinic, ClinicStaff, User
from app.services.consents import missing_required_consents


@dataclass(frozen=True)
class ClinicContext:
    user: User
    staff: ClinicStaff
    clinic: Clinic


def get_clinic_member(user: CurrentUser, db: DbSession) -> ClinicContext:
    staff = db.scalar(select(ClinicStaff).where(ClinicStaff.user_id == user.id))
    if staff is None or staff.status != STAFF_ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "not_clinic_staff", "message": "Аккаунт не связан с клиникой"},
        )
    clinic = db.get(Clinic, staff.clinic_id)
    if clinic is None:  # pragma: no cover - внешний ключ с каскадом это исключает
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "not_clinic_staff", "message": "Аккаунт не связан с клиникой"},
        )
    return ClinicContext(user=user, staff=staff, clinic=clinic)


ClinicMember = Annotated[ClinicContext, Depends(get_clinic_member)]


def get_approved_clinic_member(ctx: ClinicMember, db: DbSession) -> ClinicContext:
    if ctx.clinic.status != CLINIC_APPROVED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "clinic_not_approved",
                "message": "Клиника ещё не подтверждена или её работа приостановлена",
                "clinic_status": ctx.clinic.status,
                "status_reason": ctx.clinic.status_reason,
            },
        )
    missing = missing_required_consents(db, ctx.user.id)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "consent_required", "kinds": missing, "message": "Нужно принять актуальные согласия"},
        )
    return ctx


ApprovedClinicMember = Annotated[ClinicContext, Depends(get_approved_clinic_member)]


def _role_required(roles: tuple[str, ...]) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error": "role_required", "required": list(roles), "message": "Недостаточно прав"},
    )


def require_clinic_roles(*roles: str) -> Callable[[ApprovedClinicMember], ClinicContext]:
    """Одобренная клиника и одна из ролей внутри неё."""

    def dependency(ctx: ApprovedClinicMember) -> ClinicContext:
        if ctx.staff.role not in roles:
            raise _role_required(roles)
        return ctx

    return dependency


def require_clinic_roles_any_status(*roles: str) -> Callable[[ClinicMember], ClinicContext]:
    """Нужная роль внутри клиники, но без требования одобрения.

    Для действий, которые доступны и заявке на проверке: правка данных, документы.
    """

    def dependency(ctx: ClinicMember) -> ClinicContext:
        if ctx.staff.role not in roles:
            raise _role_required(roles)
        return ctx

    return dependency
