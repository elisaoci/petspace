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

DEMO_OWNER_EMAIL = "demo@petspace.local"


def _get_or_create_owner(db) -> User:
    user = db.scalar(select(User).where(User.email == DEMO_OWNER_EMAIL))
    if user is None:
        user = User(
            email=DEMO_OWNER_EMAIL,
            role=ROLE_OWNER,
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        db.flush()
        print(f"Создан демо-владелец: {DEMO_OWNER_EMAIL}")
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
    return user


def main() -> None:
    with SessionLocal() as db:
        owner = _get_or_create_owner(db)

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
            print(f"Seeded Макс (id={pet.id})")
        else:
            print("Макс already exists")

        # Питомцы без владельца (данные до авторизации) достаются демо-владельцу.
        orphans = db.scalars(select(Pet).where(Pet.owner_id.is_(None))).all()
        for orphan in orphans:
            orphan.owner_id = owner.id
        if orphans:
            print(f"Привязано к {DEMO_OWNER_EMAIL}: {len(orphans)} питомцев")

        db.commit()

    print(f"Вход в демо: укажите email {DEMO_OWNER_EMAIL} и код из логов backend")


if __name__ == "__main__":
    main()
