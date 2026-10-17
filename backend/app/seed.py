"""Демо-данные для локального запуска.

Создаёт владельца, согласия и питомца «Макс», а также привязывает к нему питомцев,
созданных до появления авторизации (у них `owner_id` пустой и они никому не видны).
"""

from datetime import UTC, date, datetime, timedelta
from secrets import token_urlsafe

from sqlalchemy import select

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
DEMO_OWNER_PASSWORD = "demo12345"


def _get_or_create_owner(db) -> tuple[User, bool, bool]:
    """Возвращает (владелец, создан, пароль выставлен)."""
    user = db.scalar(select(User).where(User.email == DEMO_OWNER_EMAIL))
    created = user is None
    if user is None:
        user = User(
            email=DEMO_OWNER_EMAIL,
            role=ROLE_OWNER,
            password_hash=hash_password(DEMO_OWNER_PASSWORD),
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        db.flush()
    password_set = False
    if user.password_hash is None:
        # Аккаунт из ранних версий: задаём пароль, чтобы можно было войти.
        user.password_hash = hash_password(DEMO_OWNER_PASSWORD)
        password_set = True
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
    return user, created, password_set


def main() -> None:
    """Идемпотентно: сидер можно запускать сколько угодно раз, дублей он не создаёт."""
    with SessionLocal() as db:
        owner, owner_created, password_set = _get_or_create_owner(db)
        state = "Создан" if owner_created else "Уже существует"
        print(f"{state} демо-владелец: {DEMO_OWNER_EMAIL} (id={owner.id})")
        if password_set:
            print(f"Демо-пароль выставлен: {DEMO_OWNER_PASSWORD}")

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

    print("Готово. Вход: " + DEMO_OWNER_EMAIL)
    print(f"Пароль: {DEMO_OWNER_PASSWORD} (или код из логов backend)")


if __name__ == "__main__":
    main()
