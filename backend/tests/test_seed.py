"""Сидер не должен создавать известный пароль и печатать секреты."""

from app import seed
from app.config import get_settings


def test_seed_creates_owner_without_password_when_env_is_empty(db, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "demo_owner_password", None)

    owner, created, state = seed._get_or_create_owner(db)
    db.commit()

    assert created is True
    assert state == "absent"
    assert owner.password_hash is None
    assert owner.email == seed.DEMO_OWNER_EMAIL


def test_seed_takes_password_from_environment_and_hashes_it(db, monkeypatch) -> None:
    secret = "configured-in-env-123"
    monkeypatch.setattr(get_settings(), "demo_owner_password", secret)

    owner, created, state = seed._get_or_create_owner(db)
    db.commit()

    assert created is True
    assert state == "set"
    assert owner.password_hash is not None
    # В базе только хэш: открытого пароля нет.
    assert secret not in owner.password_hash


def test_seed_does_not_overwrite_existing_password(db, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "demo_owner_password", "first-password-123")
    owner, _, _ = seed._get_or_create_owner(db)
    db.commit()
    original_hash = owner.password_hash

    monkeypatch.setattr(get_settings(), "demo_owner_password", "second-password-456")
    same_owner, created, state = seed._get_or_create_owner(db)
    db.commit()

    assert created is False
    assert state == "already"
    assert same_owner.id == owner.id
    assert same_owner.password_hash == original_hash


def test_seed_is_idempotent(db, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "demo_owner_password", None)

    first, created_first, _ = seed._get_or_create_owner(db)
    db.commit()
    second, created_second, _ = seed._get_or_create_owner(db)
    db.commit()

    assert created_first is True
    assert created_second is False
    assert second.id == first.id
