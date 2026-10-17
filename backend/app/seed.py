"""Демо-данные для локального запуска.

Скрипт **не создаёт пользователей**: аккаунт регистрируется обычным путём (через приложение
или `POST /api/v1/auth/register`), а сидер только наполняет его данными — питомцем «Макс»
и двумя событиями календаря. Пароли сидер не знает и не печатает.

Кому привязать данные: если в базе ровно один пользователь — ему. Если их несколько,
укажите email: `python -m app.seed --email you@example.com`.
"""

import argparse
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from secrets import token_urlsafe

from sqlalchemy import select

from app.database import SessionLocal
from app.models import CalendarEvent, Pet, User

PET_NAME = "Макс"


@dataclass
class SeedResult:
    owner_email: str
    created_pet: bool
    adopted_pets: int
    pet_owner_id: int | None


def resolve_owner(db, email: str | None) -> tuple[User | None, str | None]:
    """Возвращает (владелец, причина отказа)."""
    if email:
        user = db.scalar(select(User).where(User.email == email.strip().lower()))
        if user is None:
            return None, f"Пользователь {email} не найден — сначала зарегистрируйтесь"
        return user, None

    users = db.scalars(select(User).order_by(User.id)).all()
    if not users:
        return None, "В базе нет пользователей: зарегистрируйтесь на http://localhost:5173/login и запустите сидер снова"
    if len(users) > 1:
        return None, "В базе несколько пользователей: укажите владельца через --email"
    return users[0], None


def seed_demo_data(db, owner: User) -> SeedResult:
    created_pet = False
    pet = db.scalar(select(Pet).where(Pet.name == PET_NAME))

    if pet is None:
        pet = Pet(
            name=PET_NAME,
            species="dog",
            breed="Золотистый ретривер",
            sex="male",
            weight_kg=32,
            height_cm=58,
            birth_date=date(2018, 4, 12),
            owner_notes="Аллергии: не выявлены\nЗаболевания: нет",
            owner_id=owner.id,
            medical_secret_token=token_urlsafe(32),
        )
        db.add(pet)
        db.flush()
        now = datetime.now(UTC)
        db.add_all([
            CalendarEvent(pet_id=pet.id, title="Вакцинация", event_type="vaccine", starts_at=now + timedelta(days=14)),
            CalendarEvent(pet_id=pet.id, title="Прогулка", event_type="walk", starts_at=now + timedelta(hours=4)),
        ])
        created_pet = True

    # Питомцы без владельца (данные до появления авторизации) достаются этому аккаунту.
    adopted = 0
    orphans = db.scalars(select(Pet).where(Pet.owner_id.is_(None))).all()
    for orphan in orphans:
        orphan.owner_id = owner.id
        adopted += 1

    db.commit()
    return SeedResult(
        owner_email=owner.email or "",
        created_pet=created_pet,
        adopted_pets=adopted,
        pet_owner_id=pet.owner_id,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Наполнить аккаунт демо-данными: питомец «Макс» и два события календаря"
    )
    parser.add_argument("--email", help="владелец данных; нужен, если в базе больше одного пользователя")
    args = parser.parse_args()

    with SessionLocal() as db:
        owner, problem = resolve_owner(db, args.email)
        if owner is None:
            print(problem)
            return

        result = seed_demo_data(db, owner)
        print(f"Владелец: {result.owner_email} (id={owner.id})")

        if result.created_pet:
            print(f"Создан питомец «{PET_NAME}» с двумя событиями календаря")
        elif result.pet_owner_id == owner.id:
            print(f"Питомец «{PET_NAME}» уже есть у этого аккаунта")
        else:
            print(f"Питомец «{PET_NAME}» уже есть у другого аккаунта (id={result.pet_owner_id}) — пропускаю")

        if result.adopted_pets:
            print(f"Привязано к аккаунту питомцев без владельца: {result.adopted_pets}")

        print("Готово.")


if __name__ == "__main__":
    main()
