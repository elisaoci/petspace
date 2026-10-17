"""Сидер не создаёт пользователей: он наполняет данными существующий аккаунт."""

from app import seed
from app.models import CalendarEvent, Pet, User
from app.services.passwords import hash_password


def _make_user(db, email: str) -> User:
    user = User(email=email, role="owner", status="active", password_hash=hash_password("pass-1234567"))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_resolve_owner_uses_single_user(db) -> None:
    user = _make_user(db, "only@example.com")

    owner, problem = seed.resolve_owner(db, None)

    assert problem is None
    assert owner is not None
    assert owner.id == user.id


def test_resolve_owner_requires_email_when_there_are_many_users(db) -> None:
    _make_user(db, "first@example.com")
    _make_user(db, "second@example.com")

    owner, problem = seed.resolve_owner(db, None)

    assert owner is None
    assert problem is not None
    assert "несколько" in problem


def test_resolve_owner_reports_missing_email(db) -> None:
    _make_user(db, "first@example.com")

    owner, problem = seed.resolve_owner(db, "nobody@example.com")

    assert owner is None
    assert problem is not None
    assert "не найден" in problem


def test_resolve_owner_by_email(db) -> None:
    _make_user(db, "first@example.com")
    second = _make_user(db, "second@example.com")

    owner, problem = seed.resolve_owner(db, "SECOND@example.com")

    assert problem is None
    assert owner is not None
    assert owner.id == second.id


def test_seed_creates_pet_for_owner(db) -> None:
    owner = _make_user(db, "owner@example.com")

    result = seed.seed_demo_data(db, owner)

    assert result.created_pet is True
    assert result.pet_owner_id == owner.id
    pet = db.query(Pet).filter(Pet.name == seed.PET_NAME).one()
    assert pet.owner_id == owner.id
    assert db.query(CalendarEvent).count() == 2


def test_seed_is_idempotent(db) -> None:
    owner = _make_user(db, "owner@example.com")
    seed.seed_demo_data(db, owner)

    result = seed.seed_demo_data(db, owner)

    assert result.created_pet is False
    assert db.query(Pet).count() == 1
    assert db.query(CalendarEvent).count() == 2


def test_seed_adopts_pets_without_owner(db) -> None:
    owner = _make_user(db, "owner@example.com")
    db.add(Pet(name="Рекс", species="dog", medical_secret_token="orphan-token-123456"))
    db.commit()

    result = seed.seed_demo_data(db, owner)

    assert result.adopted_pets == 1
    adopted = db.query(Pet).filter(Pet.name == "Рекс").one()
    assert adopted.owner_id == owner.id


def test_seed_does_not_create_users(db) -> None:
    owner = _make_user(db, "owner@example.com")

    seed.seed_demo_data(db, owner)

    assert db.query(User).count() == 1
