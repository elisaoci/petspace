"""Операционные команды: роли и разовое шифрование уже сохранённых данных.

Примеры:
    python -m app.cli promote --email you@example.com     # выдать роль platform_admin
    python -m app.cli backfill-encryption                 # зашифровать старые заметки и сообщения
"""

import argparse

from sqlalchemy import select, text
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.database import SessionLocal
from app.models import ROLE_PLATFORM_ADMIN, ChatMessage, Pet, User


def promote(db: Session, email: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        return None
    user.role = ROLE_PLATFORM_ADMIN
    db.commit()
    return user


def backfill_encryption(db: Session) -> tuple[int, int]:
    """Пересохраняет поля, которые лежали открытым текстом до включения шифрования.

    Читаем «сырые» значения запросом: ORM уже отдаёт расшифрованный текст,
    поэтому по модели не понять, зашифровано ли хранимое значение.
    """
    from app.services.crypto import is_encrypted

    pets_updated = 0
    for pet_id, raw in db.execute(text("select id, owner_notes from pets where owner_notes is not null")).all():
        if is_encrypted(raw):
            continue
        pet = db.get(Pet, pet_id)
        if pet is None:
            continue
        pet.owner_notes = raw
        flag_modified(pet, "owner_notes")
        pets_updated += 1

    messages_updated = 0
    for message_id, raw in db.execute(text("select id, content from chat_messages")).all():
        if is_encrypted(raw):
            continue
        message = db.get(ChatMessage, message_id)
        if message is None:
            continue
        message.content = raw
        flag_modified(message, "content")
        messages_updated += 1

    db.commit()
    return pets_updated, messages_updated


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Операционные команды PetSpace")
    subparsers = parser.add_subparsers(dest="command", required=True)

    promote_parser = subparsers.add_parser("promote", help="выдать роль platform_admin")
    promote_parser.add_argument("--email", required=True)

    subparsers.add_parser("backfill-encryption", help="зашифровать старые заметки и сообщения")

    args = parser.parse_args()

    with SessionLocal() as db:
        if args.command == "promote":
            user = promote(db, args.email)
            if user is None:
                print(f"Пользователь {args.email} не найден")
                return
            print(f"Роль обновлена: {user.email} -> {user.role}")
            return

        pets_updated, messages_updated = backfill_encryption(db)
        print(f"Зашифровано: питомцев {pets_updated}, сообщений чата {messages_updated}")


if __name__ == "__main__":
    main()
