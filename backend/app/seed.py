from datetime import date, datetime, timedelta, timezone
from sqlalchemy import select
from app.database import SessionLocal
from app.models import CalendarEvent, Pet
from secrets import token_urlsafe

def main() -> None:
    with SessionLocal() as db:
        pet = db.scalar(select(Pet).where(Pet.name == "Макс"))
        if pet is None:
            pet = Pet(name="Макс", species="dog", breed="Золотистый ретривер",
                      sex="male", weight_kg=32, height_cm=58, birth_date=date(2018, 4, 12),
                      owner_notes="Аллергии: не выявлены\nЗаболевания: нет",
                      medical_secret_token=token_urlsafe(32))
            db.add(pet); db.flush()
            now = datetime.now(timezone.utc)
            db.add_all([
                CalendarEvent(pet_id=pet.id, title="Вакцинация", event_type="vaccine", starts_at=now + timedelta(days=14)),
                CalendarEvent(pet_id=pet.id, title="Прогулка", event_type="walk", starts_at=now + timedelta(hours=4)),
            ])
            db.commit()
            print(f"Seeded Макс (id={pet.id})")
        else:
            print("Макс already exists")

if __name__ == "__main__":
    main()
