"""Доступ клиники к пациенту: коды владельца, запросы по телефону, карта пациента, роли, отзыв."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ROLE_PLATFORM_ADMIN,
    AccessCode,
    AccessGrant,
    AccessRequest,
    AuditLog,
    User,
)
from tests.helpers import API_V1, register_owner
from tests.test_clinics import (
    INN_LEGAL_2,
    accept_consents,
    approve,
    as_user,
    clinic_payload,
    invite,
    staff_client,
)

CODE_RE = re.compile(r"^[A-HJKMNP-Z2-9]{4}-[A-HJKMNP-Z2-9]{4}$")
CLINIC_NAME = "Ветклиника «Айболит»"
OWNER_PHONE_RAW = "8 999 111-22-33"
OWNER_PHONE = "+79991112233"
CLINIC_ADMIN_PASSWORD = "clinic-pass-123"


# --- Фикстуры и хелперы ---------------------------------------------------------------


@pytest.fixture()
def platform_admin(client_factory, db: Session) -> TestClient:
    client = client_factory()
    tokens = register_owner(client, email="platform@example.com")
    db.get(User, tokens["user"]["id"]).role = ROLE_PLATFORM_ADMIN
    db.commit()
    return client


@pytest.fixture()
def new_clinic(client_factory):
    """Фабрика: подаёт заявку клиники и возвращает клиент её администратора."""

    def make(**overrides) -> dict:
        client = client_factory()
        response = client.post(f"{API_V1}/clinics/register", json=clinic_payload(**overrides))
        assert response.status_code == 201, response.text
        body = response.json()
        as_user(client, body)
        return {"client": client, "body": body, "id": body["clinic"]["id"]}

    return make


@pytest.fixture()
def approved_clinic(new_clinic, platform_admin) -> dict:
    clinic = new_clinic()
    approve(platform_admin, clinic["id"])
    return clinic


@pytest.fixture()
def second_clinic(new_clinic, platform_admin) -> dict:
    clinic = new_clinic(inn=INN_LEGAL_2, admin_email="second@example.com", clinic_name="Зоодоктор")
    approve(platform_admin, clinic["id"])
    return clinic


@pytest.fixture()
def make_owner(client_factory):
    """Фабрика: владелец с телефоном и одним питомцем."""

    def make(email="owner@example.com", phone=OWNER_PHONE_RAW, pet_name="Барсик") -> dict:
        client = client_factory()
        register_owner(client, email=email)
        normalized = None
        if phone is not None:
            response = client.put(f"{API_V1}/profile/phone", json={"phone": phone})
            assert response.status_code == 200, response.text
            normalized = response.json()["phone"]
        created = client.post(
            f"{API_V1}/pets",
            json={
                "name": pet_name,
                "species": "dog",
                "birth_date": "2020-03-01",
                "sex": "male",
                "owner_notes": "секретная заметка владельца",
            },
        )
        assert created.status_code == 201, created.text
        pet = created.json()
        return {"client": client, "pet": pet, "id": pet["id"], "phone": normalized}

    return make


def add_record(owner: dict, kind: str, title: str) -> None:
    response = owner["client"].post(
        f"{API_V1}/pets/{owner['id']}/records",
        json={"kind": kind, "title": title, "occurred_at": "2026-01-10T10:00:00Z"},
    )
    assert response.status_code == 201, response.text


def issue_code(owner: dict, **payload) -> dict:
    response = owner["client"].post(f"{API_V1}/pets/{owner['id']}/access-codes", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def redeem(clinic: dict, code: str):
    return clinic["client"].post(f"{API_V1}/clinics/me/access-codes/redeem", json={"code": code})


def request_access(clinic: dict, **overrides):
    payload = {"pet_name": "Барсик", "owner_phone": "+7 999 111-22-33"}
    payload.update(overrides)
    return clinic["client"].post(f"{API_V1}/clinics/me/access-requests", json=payload)


def open_by_code(owner: dict, clinic: dict, **payload) -> dict:
    """Владелец выдаёт код, клиника вводит его. Возвращает ответ redeem."""
    code = issue_code(owner, **payload)["code"]
    response = redeem(clinic, code)
    assert response.status_code == 200, response.text
    return response.json()


def clinic_grant(db: Session, clinic_id: int, pet_id: int) -> AccessGrant | None:
    db.expire_all()
    return db.scalars(
        select(AccessGrant)
        .where(AccessGrant.clinic_id == clinic_id, AccessGrant.pet_id == pet_id)
        .order_by(AccessGrant.id.desc())
    ).first()


def suspend(platform_admin: TestClient, clinic_id: int) -> None:
    response = platform_admin.post(f"{API_V1}/admin/clinics/{clinic_id}/suspend", json={"reason": "Проверка работы"})
    assert response.status_code == 200, response.text


# --- Телефон владельца ----------------------------------------------------------------


def test_owner_sets_normalizes_and_clears_phone(make_owner) -> None:
    owner = make_owner(phone=None)
    client = owner["client"]

    set_ = client.put(f"{API_V1}/profile/phone", json={"phone": "8 (999) 111-22-33"})
    cleared = client.put(f"{API_V1}/profile/phone", json={"phone": None})

    assert set_.status_code == 200
    assert set_.json() == {"phone": OWNER_PHONE}
    assert cleared.json() == {"phone": None}


def test_phone_must_be_valid_and_unique(make_owner) -> None:
    first = make_owner()
    second = make_owner(email="owner2@example.com", phone=None, pet_name="Мурка")

    assert second["client"].put(f"{API_V1}/profile/phone", json={"phone": "12-34"}).status_code == 422
    taken = second["client"].put(f"{API_V1}/profile/phone", json={"phone": OWNER_PHONE_RAW})
    assert taken.status_code == 409
    assert taken.json()["error"]["code"] == "phone_taken"
    # Свой же номер можно сохранить повторно.
    assert first["client"].put(f"{API_V1}/profile/phone", json={"phone": OWNER_PHONE_RAW}).status_code == 200


def test_phone_requires_authentication(client: TestClient) -> None:
    assert client.put(f"{API_V1}/profile/phone", json={"phone": OWNER_PHONE_RAW}).status_code == 401


# --- Код владельца: создание ----------------------------------------------------------


def test_owner_creates_code_that_expires_soon_and_is_not_stored_plain(make_owner, db: Session) -> None:
    owner = make_owner()

    created = issue_code(owner)

    assert CODE_RE.match(created["code"])
    assert created["scopes"] == ["profile", "records", "vaccinations"]
    assert created["ttl_days"] == 7
    expires = datetime.fromisoformat(created["expires_at"])
    assert timedelta(minutes=14) < expires - datetime.now(UTC) <= timedelta(minutes=15, seconds=5)
    stored = db.get(AccessCode, created["id"])
    assert stored.code_hash and stored.code_hash != created["code"].replace("-", "")
    assert "access_code.created" in [row.action for row in db.scalars(select(AuditLog)).all()]


def test_code_payload_validation(make_owner) -> None:
    owner = make_owner()
    url = f"{API_V1}/pets/{owner['id']}/access-codes"

    assert owner["client"].post(url, json={"scopes": []}).status_code == 422
    assert owner["client"].post(url, json={"scopes": ["secrets"]}).status_code == 422
    assert owner["client"].post(url, json={"ttl_days": 0}).status_code == 422
    assert owner["client"].post(url, json={"ttl_days": 366}).status_code == 422


def test_code_for_foreign_pet_is_not_found(make_owner) -> None:
    owner = make_owner()
    stranger = make_owner(email="owner2@example.com", phone="+7 999 222-33-44", pet_name="Мурка")

    response = stranger["client"].post(f"{API_V1}/pets/{owner['id']}/access-codes", json={})

    assert response.status_code == 404


def test_new_code_cancels_previous_unused_one(make_owner, approved_clinic) -> None:
    owner = make_owner()
    old = issue_code(owner)["code"]
    new = issue_code(owner)["code"]

    assert redeem(approved_clinic, old).status_code == 404
    assert redeem(approved_clinic, new).status_code == 200


def test_owner_can_revoke_unused_code(make_owner, approved_clinic) -> None:
    owner = make_owner()
    stranger = make_owner(email="owner2@example.com", phone="+7 999 222-33-44", pet_name="Мурка")
    created = issue_code(owner)

    assert stranger["client"].post(f"{API_V1}/access-codes/{created['id']}/revoke").status_code == 404
    revoked = owner["client"].post(f"{API_V1}/access-codes/{created['id']}/revoke")
    again = owner["client"].post(f"{API_V1}/access-codes/{created['id']}/revoke")

    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None
    assert again.status_code == 200
    assert redeem(approved_clinic, created["code"]).status_code == 404


def test_revoking_used_code_changes_nothing(make_owner, approved_clinic) -> None:
    owner = make_owner()
    created = issue_code(owner)
    assert redeem(approved_clinic, created["code"]).status_code == 200

    response = owner["client"].post(f"{API_V1}/access-codes/{created['id']}/revoke")

    assert response.status_code == 200
    assert response.json()["used_at"] is not None
    assert response.json()["revoked_at"] is None


# --- Код владельца: ввод в клинике ----------------------------------------------------


def test_redeem_opens_patient_and_card_is_readable(make_owner, approved_clinic, db: Session) -> None:
    owner = make_owner()
    add_record(owner, "visit", "Плановый осмотр")
    add_record(owner, "vaccination", "Бешенство")
    clinic = approved_clinic["client"]

    opened = open_by_code(owner, approved_clinic)

    assert opened["pet"]["id"] == owner["id"]
    assert opened["pet"]["name"] == "Барсик"
    assert opened["scopes"] == ["profile", "records", "vaccinations"]
    patients = clinic.get(f"{API_V1}/clinics/me/patients")
    assert [item["pet"]["id"] for item in patients.json()] == [owner["id"]]

    card = clinic.get(f"{API_V1}/clinics/me/patients/{owner['id']}")
    assert card.status_code == 200, card.text
    body = card.json()
    assert body["pet"]["name"] == "Барсик"
    assert {item["title"] for item in body["records"]} == {"Плановый осмотр", "Бешенство"}
    assert [item["title"] for item in body["vaccinations"]] == ["Бешенство"]
    assert body["grant"]["label"] == CLINIC_NAME
    assert "секретная заметка" not in card.text
    assert "owner_notes" not in card.text

    # Владелец видит доступ клиники в общем списке и может отозвать его.
    grants = owner["client"].get(f"{API_V1}/pets/{owner['id']}/access-grants").json()
    mine = [item for item in grants if item["clinic_id"] == approved_clinic["id"]]
    assert len(mine) == 1
    assert mine[0]["label"] == CLINIC_NAME
    assert "access_code.redeemed" in [row.action for row in db.scalars(select(AuditLog)).all()]


def test_code_is_single_use(make_owner, approved_clinic, second_clinic) -> None:
    owner = make_owner()
    code = issue_code(owner)["code"]

    assert redeem(approved_clinic, code).status_code == 200
    again = redeem(approved_clinic, code)
    other_clinic = redeem(second_clinic, code)

    assert again.status_code == 404
    assert again.json()["error"]["code"] == "code_invalid"
    assert other_clinic.status_code == 404


def test_code_is_accepted_in_any_reasonable_spelling(make_owner, approved_clinic) -> None:
    owner = make_owner()
    code = issue_code(owner)["code"]
    sloppy = f"  {code.lower().replace('-', ' ')}  "

    assert redeem(approved_clinic, sloppy).status_code == 200


def test_expired_code_is_rejected(make_owner, approved_clinic, db: Session) -> None:
    owner = make_owner()
    created = issue_code(owner)
    db.get(AccessCode, created["id"]).expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    assert redeem(approved_clinic, created["code"]).status_code == 404


def test_invalid_codes_are_indistinguishable(make_owner, approved_clinic, db: Session) -> None:
    owner = make_owner()
    used = issue_code(owner)["code"]
    redeem(approved_clinic, used)
    expired = issue_code(owner)
    db.get(AccessCode, expired["id"]).expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    answers = [
        redeem(approved_clinic, "ABCD-EFGH"),  # верный формат, такого кода нет
        redeem(approved_clinic, "!!!!-????"),  # неверный формат
        redeem(approved_clinic, used),  # уже использован
        redeem(approved_clinic, expired["code"]),  # истёк
    ]

    assert {response.status_code for response in answers} == {404}
    assert len({str(response.json()["error"]) for response in answers}) == 1
    assert answers[0].json()["error"]["code"] == "code_invalid"


def test_failed_attempts_are_rate_limited(make_owner, approved_clinic, monkeypatch) -> None:
    monkeypatch.setattr("app.api.patient_access.MAX_FAILED_CODE_ATTEMPTS_PER_HOUR", 3)
    owner = make_owner()
    valid = issue_code(owner)["code"]

    for _ in range(3):
        assert redeem(approved_clinic, "ABCD-EFGH").status_code == 404
    blocked = redeem(approved_clinic, valid)

    # После лимита отказывает даже верный код: иначе перебор можно продолжать.
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "too_many_attempts"


def test_failed_attempts_are_counted_per_clinic(make_owner, approved_clinic, second_clinic, monkeypatch) -> None:
    monkeypatch.setattr("app.api.patient_access.MAX_FAILED_CODE_ATTEMPTS_PER_HOUR", 2)
    owner = make_owner()
    for _ in range(2):
        redeem(approved_clinic, "ABCD-EFGH")

    code = issue_code(owner)["code"]

    assert redeem(approved_clinic, code).status_code == 429
    assert redeem(second_clinic, code).status_code == 200


def test_redeem_requires_approved_clinic_member(make_owner, new_clinic, client_factory) -> None:
    owner = make_owner()
    code = issue_code(owner)["code"]
    pending = new_clinic()

    blocked = redeem(pending, code)
    by_owner = owner["client"].post(f"{API_V1}/clinics/me/access-codes/redeem", json={"code": code})
    anonymous = client_factory().post(f"{API_V1}/clinics/me/access-codes/redeem", json={"code": code})

    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "clinic_not_approved"
    assert by_owner.status_code == 403
    assert by_owner.json()["error"]["code"] == "not_clinic_staff"
    assert anonymous.status_code == 401


def test_second_code_extends_existing_grant_instead_of_duplicating(make_owner, approved_clinic, db: Session) -> None:
    owner = make_owner()
    open_by_code(owner, approved_clinic, scopes=["profile"], ttl_days=1)
    open_by_code(owner, approved_clinic, scopes=["records"], ttl_days=30)

    db.expire_all()
    grants = db.scalars(select(AccessGrant).where(AccessGrant.clinic_id == approved_clinic["id"])).all()

    assert len(grants) == 1
    assert grants[0].scopes == ["profile", "records"]
    assert grants[0].expires_at > datetime.now(UTC) + timedelta(days=29)


# --- Запрос по имени питомца и телефону -----------------------------------------------


def test_request_reaches_owner_and_hides_patient_from_clinic(make_owner, approved_clinic) -> None:
    owner = make_owner()

    created = request_access(
        approved_clinic, message="  Запись на 15:00  ", scopes=["profile", "records"], ttl_days=3
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "pending"
    assert body["patient"] is None
    assert body["grant_id"] is None
    assert body["pet_name"] == "Барсик"
    assert body["owner_phone_masked"].endswith("33")
    assert "999" not in body["owner_phone_masked"]
    assert body["message"] == "Запись на 15:00"
    assert body["scopes"] == ["profile", "records"]
    assert body["ttl_days"] == 3
    assert body["requested_by"] == "Иванова Мария Сергеевна"

    inbox = owner["client"].get(f"{API_V1}/access-requests", params={"status": "pending"})
    assert inbox.status_code == 200
    items = inbox.json()
    assert len(items) == 1
    assert items[0]["id"] == body["id"]
    assert items[0]["clinic"]["name"] == CLINIC_NAME
    assert items[0]["pet"]["id"] == owner["id"]
    assert items[0]["message"] == "Запись на 15:00"
    assert items[0]["scopes"] == ["profile", "records"]


def test_unknown_owner_or_pet_gets_the_same_answer(make_owner, approved_clinic) -> None:
    owner = make_owner()

    matched = request_access(approved_clinic).json()
    unknown_phone = request_access(approved_clinic, owner_phone="+7 999 000-00-00").json()
    wrong_name = request_access(approved_clinic, pet_name="Рекс").json()

    for answer in (unknown_phone, wrong_name):
        assert set(answer) == set(matched)
        assert answer["status"] == "pending"
        assert answer["patient"] is None
        assert answer["grant_id"] is None
    # Владелец видит только настоящий запрос.
    assert len(owner["client"].get(f"{API_V1}/access-requests").json()) == 1


def test_pet_name_matching_ignores_case_and_spaces(make_owner, approved_clinic) -> None:
    owner = make_owner()

    assert request_access(approved_clinic, pet_name="  БАРСИК ").status_code == 201

    assert len(owner["client"].get(f"{API_V1}/access-requests").json()) == 1


def test_owner_approves_request_and_clinic_gets_access(make_owner, approved_clinic, db: Session) -> None:
    owner = make_owner()
    add_record(owner, "visit", "Осмотр")
    request_id = request_access(approved_clinic).json()["id"]
    clinic = approved_clinic["client"]
    assert clinic.get(f"{API_V1}/clinics/me/patients/{owner['id']}").status_code == 404

    approved = owner["client"].post(f"{API_V1}/access-requests/{request_id}/approve", json={})

    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    grant_id = approved.json()["grant_id"]
    assert grant_id is not None
    listed = clinic.get(f"{API_V1}/clinics/me/access-requests", params={"status": "approved"}).json()
    assert [item["id"] for item in listed] == [request_id]
    assert listed[0]["patient"]["id"] == owner["id"]
    assert listed[0]["grant_id"] == grant_id
    card = clinic.get(f"{API_V1}/clinics/me/patients/{owner['id']}")
    assert card.status_code == 200, card.text
    assert [item["title"] for item in card.json()["records"]] == ["Осмотр"]
    assert "секретная заметка" not in card.text
    assert "access_request.approved" in [row.action for row in db.scalars(select(AuditLog)).all()]


def test_owner_can_narrow_but_not_widen_request(make_owner, approved_clinic, db: Session) -> None:
    owner = make_owner()
    add_record(owner, "visit", "Осмотр")
    narrow_id = request_access(approved_clinic).json()["id"]
    url = f"{API_V1}/access-requests/{narrow_id}/approve"

    narrowed = owner["client"].post(url, json={"scopes": ["profile"], "ttl_days": 1})

    assert narrowed.status_code == 200, narrowed.text
    card = approved_clinic["client"].get(f"{API_V1}/clinics/me/patients/{owner['id']}").json()
    assert card["pet"] is not None
    assert card["records"] is None
    grant = clinic_grant(db, approved_clinic["id"], owner["id"])
    assert grant.scopes == ["profile"]
    assert grant.expires_at <= datetime.now(UTC) + timedelta(days=1, minutes=1)


def test_owner_cannot_widen_request(make_owner, approved_clinic) -> None:
    owner = make_owner()
    request_id = request_access(approved_clinic, scopes=["profile"], ttl_days=2).json()["id"]
    url = f"{API_V1}/access-requests/{request_id}/approve"

    more_scopes = owner["client"].post(url, json={"scopes": ["records"]})
    longer = owner["client"].post(url, json={"ttl_days": 30})

    assert more_scopes.status_code == 422
    assert more_scopes.json()["error"]["code"] == "scopes_not_requested"
    assert longer.status_code == 422
    assert longer.json()["error"]["code"] == "ttl_too_long"
    # Ошибочный ответ ничего не открыл.
    assert approved_clinic["client"].get(f"{API_V1}/clinics/me/patients/{owner['id']}").status_code == 404


def test_owner_denies_request(make_owner, approved_clinic) -> None:
    owner = make_owner()
    request_id = request_access(approved_clinic).json()["id"]

    denied = owner["client"].post(f"{API_V1}/access-requests/{request_id}/deny")

    assert denied.status_code == 200
    assert denied.json()["status"] == "denied"
    listed = approved_clinic["client"].get(f"{API_V1}/clinics/me/access-requests").json()
    assert listed[0]["status"] == "denied"
    assert listed[0]["patient"] is None
    assert approved_clinic["client"].get(f"{API_V1}/clinics/me/patients/{owner['id']}").status_code == 404


def test_request_cannot_be_decided_twice(make_owner, approved_clinic) -> None:
    owner = make_owner()
    first = request_access(approved_clinic).json()["id"]
    assert owner["client"].post(f"{API_V1}/access-requests/{first}/approve", json={}).status_code == 200

    deny_after = owner["client"].post(f"{API_V1}/access-requests/{first}/deny")
    approve_again = owner["client"].post(f"{API_V1}/access-requests/{first}/approve", json={})

    assert deny_after.status_code == 409
    assert deny_after.json()["error"]["code"] == "invalid_status"
    assert deny_after.json()["error"]["details"]["current"] == "approved"
    assert approve_again.status_code == 409


def test_denied_request_cannot_be_approved(make_owner, approved_clinic) -> None:
    owner = make_owner()
    request_id = request_access(approved_clinic).json()["id"]
    owner["client"].post(f"{API_V1}/access-requests/{request_id}/deny")

    response = owner["client"].post(f"{API_V1}/access-requests/{request_id}/approve", json={})

    assert response.status_code == 409
    assert response.json()["error"]["details"]["current"] == "denied"


def test_expired_request_cannot_be_approved(make_owner, approved_clinic, db: Session) -> None:
    owner = make_owner()
    request_id = request_access(approved_clinic).json()["id"]
    db.get(AccessRequest, request_id).expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()

    clinic_view = approved_clinic["client"].get(f"{API_V1}/clinics/me/access-requests", params={"status": "expired"})
    pending_view = approved_clinic["client"].get(f"{API_V1}/clinics/me/access-requests", params={"status": "pending"})
    owner_view = owner["client"].get(f"{API_V1}/access-requests", params={"status": "expired"})
    attempt = owner["client"].post(f"{API_V1}/access-requests/{request_id}/approve", json={})

    assert [item["id"] for item in clinic_view.json()] == [request_id]
    assert clinic_view.json()[0]["status"] == "expired"
    assert pending_view.json() == []
    assert [item["status"] for item in owner_view.json()] == ["expired"]
    assert attempt.status_code == 409
    assert attempt.json()["error"]["details"]["current"] == "expired"


def test_other_owner_cannot_see_or_decide_request(make_owner, approved_clinic) -> None:
    owner = make_owner()
    stranger = make_owner(email="owner2@example.com", phone="+7 999 222-33-44", pet_name="Мурка")
    request_id = request_access(approved_clinic).json()["id"]
    assert owner["client"].get(f"{API_V1}/access-requests").json()

    assert stranger["client"].get(f"{API_V1}/access-requests").json() == []
    assert stranger["client"].post(f"{API_V1}/access-requests/{request_id}/approve", json={}).status_code == 404
    assert stranger["client"].post(f"{API_V1}/access-requests/{request_id}/deny").status_code == 404


def test_duplicate_open_request_is_rejected(make_owner, approved_clinic, second_clinic) -> None:
    make_owner()
    first = request_access(approved_clinic)
    assert first.status_code == 201

    duplicate = request_access(approved_clinic, pet_name=" барсик ")
    other_clinic = request_access(second_clinic)
    approved_clinic["client"].post(f"{API_V1}/clinics/me/access-requests/{first.json()['id']}/cancel")
    after_cancel = request_access(approved_clinic)

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "request_pending"
    assert other_clinic.status_code == 201
    assert after_cancel.status_code == 201


def test_clinic_cancels_own_request(make_owner, approved_clinic, second_clinic) -> None:
    owner = make_owner()
    request_id = request_access(approved_clinic).json()["id"]
    url = f"{API_V1}/clinics/me/access-requests/{request_id}/cancel"

    foreign = second_clinic["client"].post(url)
    cancelled = approved_clinic["client"].post(url)
    again = approved_clinic["client"].post(url)
    approve_attempt = owner["client"].post(f"{API_V1}/access-requests/{request_id}/approve", json={})

    assert foreign.status_code == 404
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert again.status_code == 409
    assert approve_attempt.status_code == 409
    assert approve_attempt.json()["error"]["details"]["current"] == "cancelled"


def test_requests_are_limited_per_day(make_owner, approved_clinic, monkeypatch) -> None:
    monkeypatch.setattr("app.api.patient_access.MAX_REQUESTS_PER_DAY", 2)
    make_owner()

    assert request_access(approved_clinic, pet_name="Один").status_code == 201
    assert request_access(approved_clinic, pet_name="Два").status_code == 201
    limited = request_access(approved_clinic, pet_name="Три")

    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "too_many_requests"


def test_request_payload_validation(approved_clinic) -> None:
    for overrides in (
        {"owner_phone": "12-34"},
        {"pet_name": "   "},
        {"ttl_days": 0},
        {"ttl_days": 366},
        {"scopes": []},
        {"scopes": ["secrets"]},
        {"message": "x" * 501},
    ):
        assert request_access(approved_clinic, **overrides).status_code == 422, overrides


def test_suspended_clinic_requests_are_hidden_and_not_approvable(make_owner, approved_clinic, platform_admin) -> None:
    owner = make_owner()
    request_id = request_access(approved_clinic).json()["id"]
    suspend(platform_admin, approved_clinic["id"])

    inbox = owner["client"].get(f"{API_V1}/access-requests", params={"status": "pending"})
    attempt = owner["client"].post(f"{API_V1}/access-requests/{request_id}/approve", json={})

    assert inbox.json() == []
    assert attempt.status_code == 409
    assert attempt.json()["error"]["code"] == "clinic_unavailable"


def test_request_endpoints_need_approved_clinic(new_clinic, make_owner) -> None:
    make_owner()
    pending = new_clinic()

    assert request_access(pending).status_code == 403
    assert pending["client"].get(f"{API_V1}/clinics/me/access-requests").status_code == 403


# --- Пациенты и карта -----------------------------------------------------------------


def test_patients_are_listed_per_clinic_and_paginated(make_owner, approved_clinic, second_clinic) -> None:
    first = make_owner()
    second = make_owner(email="owner2@example.com", phone="+7 999 222-33-44", pet_name="Мурка")
    open_by_code(first, approved_clinic)
    open_by_code(second, approved_clinic)

    listing = approved_clinic["client"].get(f"{API_V1}/clinics/me/patients", params={"limit": 1, "offset": 0})
    other = second_clinic["client"].get(f"{API_V1}/clinics/me/patients")

    assert listing.status_code == 200
    assert listing.headers["X-Total-Count"] == "2"
    assert len(listing.json()) == 1
    assert listing.json()[0]["pet"]["id"] == second["id"]  # свежие доступы выше
    assert other.json() == []


def test_card_needs_grant_of_this_clinic(make_owner, approved_clinic, second_clinic) -> None:
    owner = make_owner()
    open_by_code(owner, approved_clinic)

    assert second_clinic["client"].get(f"{API_V1}/clinics/me/patients/{owner['id']}").status_code == 404
    assert approved_clinic["client"].get(f"{API_V1}/clinics/me/patients/999999").status_code == 404
    assert owner["client"].get(f"{API_V1}/clinics/me/patients/{owner['id']}").status_code == 403


def test_card_respects_granted_scopes(make_owner, approved_clinic) -> None:
    owner = make_owner()
    add_record(owner, "visit", "Осмотр")
    add_record(owner, "vaccination", "Бешенство")
    open_by_code(owner, approved_clinic, scopes=["vaccinations"])

    card = approved_clinic["client"].get(f"{API_V1}/clinics/me/patients/{owner['id']}").json()

    assert card["pet"] is None
    assert card["records"] is None
    assert [item["title"] for item in card["vaccinations"]] == ["Бешенство"]


def test_card_read_is_audited_and_marks_last_use(make_owner, approved_clinic, db: Session) -> None:
    owner = make_owner()
    open_by_code(owner, approved_clinic)
    assert clinic_grant(db, approved_clinic["id"], owner["id"]).last_used_at is None

    approved_clinic["client"].get(f"{API_V1}/clinics/me/patients/{owner['id']}")

    assert clinic_grant(db, approved_clinic["id"], owner["id"]).last_used_at is not None
    logs = db.scalars(select(AuditLog).where(AuditLog.action == "patient.read")).all()
    assert len(logs) == 1
    assert logs[0].entity_id == owner["id"]
    assert logs[0].details["clinic_id"] == approved_clinic["id"]


def test_owner_revocation_closes_access_immediately(make_owner, approved_clinic) -> None:
    owner = make_owner()
    opened = open_by_code(owner, approved_clinic)
    clinic = approved_clinic["client"]
    assert clinic.get(f"{API_V1}/clinics/me/patients/{owner['id']}").status_code == 200

    revoked = owner["client"].post(f"{API_V1}/access-grants/{opened['grant_id']}/revoke")

    assert revoked.status_code == 200
    assert clinic.get(f"{API_V1}/clinics/me/patients/{owner['id']}").status_code == 404
    assert clinic.get(f"{API_V1}/clinics/me/patients").json() == []


def test_expired_grant_closes_access(make_owner, approved_clinic, db: Session) -> None:
    owner = make_owner()
    opened = open_by_code(owner, approved_clinic)
    db.expire_all()
    db.get(AccessGrant, opened["grant_id"]).expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    clinic = approved_clinic["client"]

    assert clinic.get(f"{API_V1}/clinics/me/patients/{owner['id']}").status_code == 404
    assert clinic.get(f"{API_V1}/clinics/me/patients").json() == []


def test_suspended_clinic_loses_access_and_regains_it_on_approval(
    make_owner, approved_clinic, platform_admin
) -> None:
    owner = make_owner()
    open_by_code(owner, approved_clinic)
    clinic = approved_clinic["client"]
    suspend(platform_admin, approved_clinic["id"])

    blocked = clinic.get(f"{API_V1}/clinics/me/patients/{owner['id']}")
    approve(platform_admin, approved_clinic["id"])

    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "clinic_not_approved"
    assert clinic.get(f"{API_V1}/clinics/me/patients/{owner['id']}").status_code == 200


def test_registrar_sees_profile_only_while_doctor_sees_everything(
    make_owner, approved_clinic, client_factory
) -> None:
    owner = make_owner()
    add_record(owner, "visit", "Осмотр")
    open_by_code(owner, approved_clinic)
    registrar = staff_client(client_factory, approved_clinic, "reg@aibolit.example", role="clinic_registrar")
    doctor = staff_client(client_factory, approved_clinic, "doctor@aibolit.example", role="clinic_doctor")
    accept_consents(registrar)
    accept_consents(doctor)
    path = f"{API_V1}/clinics/me/patients/{owner['id']}"

    registrar_card = registrar.get(path).json()
    doctor_card = doctor.get(path).json()
    registrar_list = registrar.get(f"{API_V1}/clinics/me/patients").json()

    assert registrar_card["pet"]["name"] == "Барсик"
    assert registrar_card["records"] is None
    assert registrar_card["grant"]["scopes"] == ["profile"]
    assert registrar_list[0]["scopes"] == ["profile"]
    assert [item["title"] for item in doctor_card["records"]] == ["Осмотр"]


def test_deleting_pet_removes_codes_requests_and_grants(make_owner, approved_clinic, db: Session) -> None:
    owner = make_owner()
    issue_code(owner)
    open_by_code(owner, approved_clinic)
    request_access(approved_clinic)

    deleted = owner["client"].delete(f"{API_V1}/pets/{owner['id']}")

    assert deleted.status_code == 204
    db.expire_all()
    assert db.scalars(select(AccessCode).where(AccessCode.pet_id == owner["id"])).all() == []
    assert db.scalars(select(AccessRequest).where(AccessRequest.pet_id == owner["id"])).all() == []
    assert db.scalars(select(AccessGrant).where(AccessGrant.pet_id == owner["id"])).all() == []


# --- Справочник клиник ----------------------------------------------------------------


def test_directory_lists_only_approved_clinics(make_owner, approved_clinic, new_clinic, client_factory) -> None:
    new_clinic(inn=INN_LEGAL_2, admin_email="pending@example.com", clinic_name="Ожидающая клиника")
    owner = make_owner()

    listing = owner["client"].get(f"{API_V1}/clinics/directory")
    found = owner["client"].get(f"{API_V1}/clinics/directory", params={"q": "Айб"})
    missing = owner["client"].get(f"{API_V1}/clinics/directory", params={"q": "zzz"})

    assert listing.status_code == 200
    assert listing.headers["X-Total-Count"] == "1"
    assert [item["name"] for item in listing.json()] == [CLINIC_NAME]
    assert set(listing.json()[0]) == {"id", "name", "address", "phone"}
    assert [item["id"] for item in found.json()] == [approved_clinic["id"]]
    assert missing.json() == []
    assert client_factory().get(f"{API_V1}/clinics/directory").status_code == 401


# --- Защита последнего администратора -------------------------------------------------


def test_last_clinic_admin_cannot_delete_account(approved_clinic) -> None:
    clinic = approved_clinic["client"]
    payload = {"confirm": True, "password": CLINIC_ADMIN_PASSWORD}

    blocked = clinic.post(f"{API_V1}/account/delete", json=payload)

    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "last_admin"

    assert invite(clinic, email="second-admin@aibolit.example", role="clinic_admin").status_code == 201
    assert clinic.post(f"{API_V1}/account/delete", json=payload).status_code == 204
