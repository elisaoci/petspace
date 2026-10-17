"""Демо-данные для локального запуска.

Создаёт владельца, согласия и питомца «Макс», а также привязывает к нему питомцев,
созданных до появления авторизации (у них `owner_id` пустой и они никому не видны).

Пароль демо-владельца берётся только из окружения (`DEMO_OWNER_PASSWORD`) и никогда
не печатается: секреты не должны попадать в логи и историю терминала. Без переменной
аккаунт создаётся без пароля, и вход идёт по коду с почты.
"""

from datetime import UTC, date, datetime, timedelta
from secrets import token_urlsafe

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import (
    CONSENT_VERSIONS,
    REQUIRED_CONSENTS,
    ROLE_OWNER,
    CalendarEvent,
    Consent,
    Pet,
    User,
)
from app.services.passwords import hash_password

DEMO_OWNER_EMAIL = "demo@petspace.local"


def _get_or_create_owner(db) -> tuple[User, bool, str]:
    """Возвращает (владелец, создан, состояние пароля).

    Состояние пароля: "set" — задан из окружения, "absent" — пароля нет,
    "already" — пароль уже был, не перезаписываем.
    """
    configured_password = get_settings().demo_owner_password
    user = db.scalar(select(User).where(User.email == DEMO_OWNER_EMAIL))
    created = user is None
    if user is None:
        user = User(
            email=DEMO_OWNER_EMAIL,
            role=ROLE_OWNER,
            password_hash=hash_password(configured_password) if configured_password else None,
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        db.flush()
        password_state = "set" if configured_password else "absent"
    elif user.password_hash is None:
        if configured_password:
            user.password_hash = hash_password(configured_password)
            password_state = "set"
        else:
            password_state = "absent"
    else:
        password_state = "already"
    for kind in REQUIRED_CONSENTS:
        accepted = db.scalar(
            select(Consent).where(
                Consent.user_id == user.id,
                Consent.kind == kind,
                Consent.version == CONSENT_VERSIONS[kind],
            )
        )
        if accepted is None:
            db.add(Consent(user_id=user.id, kind=kind, version=CONSENT_VERSIONS[kind]))
    return user, created, password_state


def main() -> None:
    """Идемпотентно: сидер можно запускать сколько угодно раз, дублей он не создаёт."""
    with SessionLocal() as db:
        owner, owner_created, password_state = _get_or_create_owner(db)
        state = "Создан" if owner_created else "Уже существует"
        print(f"{state} демо-владелец: {DEMO_OWNER_EMAIL} (id={owner.id})")

        pet = db.scalar(select(Pet).where(Pet.name == "Макс"))
        if pet is None:
            pet = Pet(name="Макс", species="dog", breed="Золотистый ретривер",
                      sex="male", weight_kg=32, height_cm=58, birth_date=date(2018, 4, 12),
                      owner_notes="Аллергии: не выявлены\nЗаболевания: нет",
                      owner_id=owner.id,
                      medical_secret_token=token_urlsafe(32))
            db.add(pet)
            db.flush()
            now = datetime.now(UTC)
            db.add_all([
                CalendarEvent(pet_id=pet.id, title="Вакцинация", event_type="vaccine", starts_at=now + timedelta(days=14)),
                CalendarEvent(pet_id=pet.id, title="Прогулка", event_type="walk", starts_at=now + timedelta(hours=4)),
            ])
            print(f"Создан питомец «Макс» (id={pet.id}) с двумя событиями календаря")
        else:
            print(f"Питомец «Макс» уже есть (id={pet.id})")
            if pet.owner_id != owner.id:
                pet.owner_id = owner.id
                print(f"«Макс» привязан к {DEMO_OWNER_EMAIL}")

        # Питомцы без владельца (данные до авторизации) достаются демо-владельцу.
        orphans = db.scalars(select(Pet).where(Pet.owner_id.is_(None))).all()
        for orphan in orphans:
            orphan.owner_id = owner.id
        if orphans:
            print(f"Привязано к {DEMO_OWNER_EMAIL} питомцев без владельца: {len(orphans)}")

        db.commit()

    print("Готово. Аккаунт: " + DEMO_OWNER_EMAIL)
    if password_state == "set":
        print("Пароль задан из DEMO_OWNER_PASSWORD (в вывод не выводится).")
    elif password_state == "already":
        print("Пароль уже был задан — не перезаписываю.")
    else:
        print("Пароля нет: вход по коду с почты, код придёт в логи backend.")
        print("Чтобы включить вход по паролю, задайте DEMO_OWNER_PASSWORD в .env и запустите сидер снова.")


if __name__ == "__main__":
    main()
