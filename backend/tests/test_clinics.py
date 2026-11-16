"""Основа клиники: заявка, модерация, документы, сотрудники, изоляция между клиниками."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ROLE_CLINIC_ADMIN,
    ROLE_CLINIC_DOCTOR,
    ROLE_PLATFORM_ADMIN,
    AuditLog,
    Clinic,
    ClinicStaff,
    User,
)
from app.services.clinics import MAX_DOCUMENT_BYTES, MAX_DOCUMENTS_PER_CLINIC
from tests.conftest import FakeEmailSender
from tests.helpers import (
    API_V1,
    confirm_password_reset,
    consents_payload,
    login,
    register_owner,
    request_reset_code,
)

# Настоящие контрольные цифры: 10 цифр — юрлицо, 12 — индивидуальный предприниматель.
INN_LEGAL = "7707083893"
INN_LEGAL_2 = "7736207543"
INN_ENTREPRENEUR = "500100732570"
PDF = b"%PDF-1.4\n%petspace test document\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
STAFF_PASSWORD = "staff-pass-123"


# --- Фикстуры и хелперы ---------------------------------------------------------------


def clinic_payload(**overrides) -> dict:
    payload = {
        "clinic_name": "Ветклиника «Айболит»",
        "inn": INN_LEGAL,
        "address": "г. Москва, ул. Тверская, д. 1",
        "phone": "+7 (495) 123-45-67",
        "email": "info@aibolit.example",
        "contact_name": "Иванова Мария Сергеевна",
        "admin_email": "admin@aibolit.example",
        "password": "clinic-pass-123",
        "consents": consents_payload(),
    }
    payload.update(overrides)
    return payload


def as_user(client: TestClient, tokens: dict) -> TestClient:
    client.headers["Authorization"] = f"Bearer {tokens['access_token']}"
    return client


@pytest.fixture()
def clinic_mailbox(monkeypatch) -> FakeEmailSender:
    """Перехватывает письма клиникам (заявка, решение модератора, приглашение сотрудника)."""
    sender = FakeEmailSender()
    monkeypatch.setattr("app.services.clinics.get_email_sender", lambda: sender)
    return sender


@pytest.fixture()
def platform_admin(client_factory, db: Session) -> TestClient:
    client = client_factory()
    tokens = register_owner(client, email="platform@example.com")
    db.get(User, tokens["user"]["id"]).role = ROLE_PLATFORM_ADMIN
    db.commit()
    return client


@pytest.fixture()
def new_clinic(client_factory):
    """Фабрика: подаёт заявку и возвращает клиент администратора клиники вместе с ответом."""

    def make(**overrides) -> dict:
        client = client_factory()
        response = client.post(f"{API_V1}/clinics/register", json=clinic_payload(**overrides))
        assert response.status_code == 201, response.text
        body = response.json()
        as_user(client, body)
        return {"client": client, "body": body, "id": body["clinic"]["id"]}

    return make


@pytest.fixture()
def clinic(new_clinic) -> dict:
    """Клиника в статусе pending."""
    return new_clinic()


def approve(platform_admin: TestClient, clinic_id: int) -> None:
    response = platform_admin.post(f"{API_V1}/admin/clinics/{clinic_id}/approve")
    assert response.status_code == 200, response.text


@pytest.fixture()
def approved_clinic(clinic, platform_admin) -> dict:
    approve(platform_admin, clinic["id"])
    return clinic


def upload(client: TestClient, content: bytes = PDF, filename: str = "license.pdf", title: str | None = None):
    data = {"title": title} if title else {}
    return client.post(
        f"{API_V1}/clinics/me/documents",
        files={"file": (filename, content, "application/octet-stream")},
        data=data,
    )


def invite(client: TestClient, email: str = "doctor@aibolit.example", role: str = "clinic_doctor", **extra):
    payload = {"email": email, "full_name": "Петров Пётр Петрович", "role": role}
    payload.update(extra)
    return client.post(f"{API_V1}/clinics/me/staff", json=payload)


def staff_client(client_factory, approved: dict, email: str, role: str = "clinic_doctor") -> TestClient:
    """Приглашает сотрудника и проходит весь путь: код на почту, пароль, вход."""
    response = invite(approved["client"], email=email, role=role)
    assert response.status_code == 201, response.text
    client = client_factory()
    code = request_reset_code(client, email)
    result = confirm_password_reset(client, email, code, STAFF_PASSWORD)
    assert result["status_code"] == 200, result["body"]
    return as_user(client, result["body"])


def accept_consents(client: TestClient) -> None:
    response = client.post(f"{API_V1}/auth/consents", json={"consents": consents_payload()})
    assert response.status_code == 201, response.text


def audit_actions(db: Session) -> list[str]:
    return list(db.scalars(select(AuditLog.action)).all())


# --- Заявка организации ---------------------------------------------------------------


def test_register_creates_pending_clinic_and_admin_account(
    client_factory, db: Session, clinic_mailbox: FakeEmailSender
) -> None:
    client = client_factory()

    response = client.post(f"{API_V1}/clinics/register", json=clinic_payload())

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["user"]["role"] == ROLE_CLINIC_ADMIN
    assert body["user"]["consents_accepted"] is True
    assert body["clinic"]["status"] == "pending"
    assert body["clinic"]["inn"] == INN_LEGAL
    assert body["clinic"]["phone"] == "+74951234567"

    clinic = db.get(Clinic, body["clinic"]["id"])
    staff = db.scalar(select(ClinicStaff).where(ClinicStaff.clinic_id == clinic.id))
    assert clinic.created_by_id == body["user"]["id"]
    assert staff.user_id == body["user"]["id"]
    assert staff.role == ROLE_CLINIC_ADMIN
    assert staff.full_name == "Иванова Мария Сергеевна"
    assert "clinic.registered" in audit_actions(db)
    assert clinic_mailbox.messages[-1]["to"] == "admin@aibolit.example"


def test_registered_admin_can_log_in_with_regular_login(client_factory, clinic) -> None:
    client = client_factory()

    result = login(client, "admin@aibolit.example", "clinic-pass-123")

    assert result["status_code"] == 200
    assert result["body"]["user"]["role"] == ROLE_CLINIC_ADMIN


def test_register_requires_consents(client: TestClient) -> None:
    response = client.post(f"{API_V1}/clinics/register", json=clinic_payload(consents=[]))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "consent_required"


@pytest.mark.parametrize("inn", ["1234567890", "123", "77070838931", "abcdefghij", "7707083894"])
def test_register_rejects_invalid_inn(client: TestClient, inn: str) -> None:
    response = client.post(f"{API_V1}/clinics/register", json=clinic_payload(inn=inn))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_register_accepts_entrepreneur_inn(client: TestClient) -> None:
    response = client.post(f"{API_V1}/clinics/register", json=clinic_payload(inn=INN_ENTREPRENEUR))

    assert response.status_code == 201, response.text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("8 (999) 123-45-67", "+79991234567"), ("+79991234567", "+79991234567"), ("9991234567", "+79991234567")],
)
def test_register_normalizes_phone(client: TestClient, raw: str, expected: str) -> None:
    response = client.post(f"{API_V1}/clinics/register", json=clinic_payload(phone=raw))

    assert response.status_code == 201, response.text
    assert response.json()["clinic"]["phone"] == expected


def test_register_rejects_bad_phone_and_weak_password(client: TestClient) -> None:
    assert client.post(f"{API_V1}/clinics/register", json=clinic_payload(phone="12-34")).status_code == 422
    assert client.post(f"{API_V1}/clinics/register", json=clinic_payload(password="short")).status_code == 422


def test_register_rejects_taken_email(client_factory, clinic) -> None:
    other = client_factory()
    register_owner(other, email="owner@example.com")

    again = client_factory().post(
        f"{API_V1}/clinics/register",
        json=clinic_payload(inn=INN_LEGAL_2, admin_email="admin@aibolit.example"),
    )
    owner_email = client_factory().post(
        f"{API_V1}/clinics/register",
        json=clinic_payload(inn=INN_LEGAL_2, admin_email="owner@example.com"),
    )

    assert again.status_code == 409
    assert again.json()["error"]["code"] == "email_taken"
    assert owner_email.status_code == 409


def test_register_rejects_same_clinic_but_allows_other_branch(client_factory, clinic) -> None:
    duplicate = client_factory().post(
        f"{API_V1}/clinics/register",
        json=clinic_payload(
            admin_email="second@aibolit.example",
            address="Г. МОСКВА, УЛ. ТВЕРСКАЯ, Д. 1",  # тот же адрес другим регистром
        ),
    )
    branch = client_factory().post(
        f"{API_V1}/clinics/register",
        json=clinic_payload(admin_email="branch@aibolit.example", address="г. Москва, ул. Арбат, д. 5"),
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "clinic_exists"
    assert branch.status_code == 201, branch.text


# --- Доступ: кто что может -------------------------------------------------------------


def test_owner_has_no_clinic_access(client_factory) -> None:
    owner = client_factory()
    register_owner(owner, email="owner@example.com")

    response = owner.get(f"{API_V1}/clinics/me")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_clinic_staff"


def test_clinic_endpoints_require_authentication(client: TestClient) -> None:
    assert client.get(f"{API_V1}/clinics/me").status_code == 401
    assert client.get(f"{API_V1}/clinics/me/staff").status_code == 401


def test_clinic_admin_sees_own_clinic_and_status(clinic) -> None:
    response = clinic["client"].get(f"{API_V1}/clinics/me")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == clinic["id"]
    assert body["status"] == "pending"
    assert body["my_role"] == ROLE_CLINIC_ADMIN
    assert body["my_full_name"] == "Иванова Мария Сергеевна"


def test_pending_clinic_cannot_manage_staff(clinic) -> None:
    listing = clinic["client"].get(f"{API_V1}/clinics/me/staff")
    invited = invite(clinic["client"])

    for response in (listing, invited):
        assert response.status_code == 403
        error = response.json()["error"]
        assert error["code"] == "clinic_not_approved"
        assert error["details"]["clinic_status"] == "pending"


def test_clinic_user_is_not_platform_admin(clinic) -> None:
    response = clinic["client"].get(f"{API_V1}/admin/clinics")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "role_required"


def test_clinic_user_cannot_see_owner_data(clinic) -> None:
    response = clinic["client"].get(f"{API_V1}/pets")

    assert response.status_code == 200
    assert response.json() == []


# --- Модерация -------------------------------------------------------------------------


def test_admin_sees_moderation_queue(platform_admin, new_clinic) -> None:
    first = new_clinic()
    second = new_clinic(inn=INN_LEGAL_2, admin_email="second@example.com", clinic_name="Зоодоктор")
    upload(first["client"])

    response = platform_admin.get(f"{API_V1}/admin/clinics", params={"status": "pending"})

    assert response.status_code == 200, response.text
    assert response.headers["X-Total-Count"] == "2"
    rows = response.json()
    # В очереди заявки идут от старых к новым.
    assert [row["id"] for row in rows] == [first["id"], second["id"]]
    assert rows[0]["documents_count"] == 1
    assert rows[0]["staff_count"] == 1
    assert rows[1]["documents_count"] == 0


def test_admin_filters_and_searches_clinics(platform_admin, new_clinic) -> None:
    first = new_clinic()
    new_clinic(inn=INN_LEGAL_2, admin_email="second@example.com", clinic_name="Зоодоктор")
    approve(platform_admin, first["id"])

    approved = platform_admin.get(f"{API_V1}/admin/clinics", params={"status": "approved"}).json()
    by_name = platform_admin.get(f"{API_V1}/admin/clinics", params={"q": "Зоо"}).json()
    by_inn = platform_admin.get(f"{API_V1}/admin/clinics", params={"q": "77070"}).json()
    percent = platform_admin.get(f"{API_V1}/admin/clinics", params={"q": "%"}).json()

    assert [row["id"] for row in approved] == [first["id"]]
    assert [row["name"] for row in by_name] == ["Зоодоктор"]
    assert [row["id"] for row in by_inn] == [first["id"]]
    assert percent == []
    assert platform_admin.get(f"{API_V1}/admin/clinics", params={"status": "bogus"}).status_code == 422


def test_admin_sees_clinic_detail(platform_admin, clinic) -> None:
    upload(clinic["client"], title="Лицензия")

    response = platform_admin.get(f"{API_V1}/admin/clinics/{clinic['id']}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created_by_email"] == "admin@aibolit.example"
    assert body["moderated_by_email"] is None
    assert [member["email"] for member in body["staff"]] == ["admin@aibolit.example"]
    assert body["documents"][0]["title"] == "Лицензия"
    assert "content" not in body["documents"][0]
    assert platform_admin.get(f"{API_V1}/admin/clinics/9999").status_code == 404


def test_only_platform_admin_can_moderate(clinic, client_factory) -> None:
    owner = client_factory()
    register_owner(owner, email="owner@example.com")

    for caller in (clinic["client"], owner):
        assert caller.post(f"{API_V1}/admin/clinics/{clinic['id']}/approve").status_code == 403
        rejected = caller.post(f"{API_V1}/admin/clinics/{clinic['id']}/reject", json={"reason": "Причина отказа"})
        assert rejected.status_code == 403
    assert client_factory().post(f"{API_V1}/admin/clinics/{clinic['id']}/approve").status_code == 401


def test_approve_opens_clinic_and_notifies_admin(
    platform_admin, clinic, db: Session, clinic_mailbox: FakeEmailSender
) -> None:
    response = platform_admin.post(f"{API_V1}/admin/clinics/{clinic['id']}/approve")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"
    assert response.json()["moderated_at"] is not None
    assert clinic["client"].get(f"{API_V1}/clinics/me/staff").status_code == 200
    assert "clinic.approved" in audit_actions(db)
    assert clinic_mailbox.messages[-1]["to"] == "admin@aibolit.example"
    assert "подключена" in clinic_mailbox.messages[-1]["subject"]
    detail = platform_admin.get(f"{API_V1}/admin/clinics/{clinic['id']}").json()
    assert detail["moderated_by_email"] == "platform@example.com"


def test_reject_requires_reason_and_shows_it_to_clinic(
    platform_admin, clinic, clinic_mailbox: FakeEmailSender
) -> None:
    url = f"{API_V1}/admin/clinics/{clinic['id']}/reject"

    assert platform_admin.post(url, json={}).status_code == 422
    assert platform_admin.post(url, json={"reason": "  "}).status_code == 422

    response = platform_admin.post(url, json={"reason": "Не приложена лицензия"})

    assert response.status_code == 200, response.text
    mine = clinic["client"].get(f"{API_V1}/clinics/me").json()
    assert mine["status"] == "rejected"
    assert mine["status_reason"] == "Не приложена лицензия"
    assert "Не приложена лицензия" in clinic_mailbox.messages[-1]["text"]


def test_rejected_clinic_can_fix_and_resubmit(platform_admin, clinic) -> None:
    platform_admin.post(f"{API_V1}/admin/clinics/{clinic['id']}/reject", json={"reason": "Неверный адрес"})
    me = clinic["client"]

    fixed = me.patch(f"{API_V1}/clinics/me", json={"address": "г. Москва, ул. Тверская, д. 2"})
    resubmitted = me.post(f"{API_V1}/clinics/me/resubmit")

    assert fixed.status_code == 200, fixed.text
    assert resubmitted.status_code == 200, resubmitted.text
    assert resubmitted.json()["status"] == "pending"
    assert resubmitted.json()["status_reason"] is None
    assert me.post(f"{API_V1}/clinics/me/resubmit").status_code == 409


def test_invalid_status_transitions_are_rejected(platform_admin, clinic) -> None:
    base = f"{API_V1}/admin/clinics/{clinic['id']}"

    suspend_pending = platform_admin.post(f"{base}/suspend", json={"reason": "Проверка"})
    assert suspend_pending.status_code == 409
    error = suspend_pending.json()["error"]
    assert error["code"] == "invalid_status"
    assert error["details"]["current"] == "pending"

    approve(platform_admin, clinic["id"])
    assert platform_admin.post(f"{base}/approve").status_code == 409
    assert platform_admin.post(f"{base}/reject", json={"reason": "Передумали"}).status_code == 409


def test_suspend_closes_clinic_and_approve_reopens_it(platform_admin, approved_clinic) -> None:
    me = approved_clinic["client"]
    base = f"{API_V1}/admin/clinics/{approved_clinic['id']}"
    assert me.get(f"{API_V1}/clinics/me/staff").status_code == 200

    suspended = platform_admin.post(f"{base}/suspend", json={"reason": "Жалобы владельцев"})

    assert suspended.status_code == 200, suspended.text
    blocked = me.get(f"{API_V1}/clinics/me/staff")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "clinic_not_approved"
    assert blocked.json()["error"]["details"]["status_reason"] == "Жалобы владельцев"
    assert me.get(f"{API_V1}/clinics/me").json()["status"] == "suspended"

    approve(platform_admin, approved_clinic["id"])
    assert me.get(f"{API_V1}/clinics/me/staff").status_code == 200


# --- Профиль клиники ------------------------------------------------------------------


def test_admin_updates_profile(clinic, db: Session) -> None:
    me = clinic["client"]

    response = me.patch(
        f"{API_V1}/clinics/me",
        json={"name": "Айболит Плюс", "phone": "8 999 111-22-33", "email": ""},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Айболит Плюс"
    assert body["phone"] == "+79991112233"
    assert body["email"] is None
    assert "clinic.updated" in audit_actions(db)


def test_profile_update_validation(clinic) -> None:
    me = clinic["client"]
    url = f"{API_V1}/clinics/me"

    assert me.patch(url, json={}).status_code == 422
    assert me.patch(url, json={"inn": "1234567890"}).status_code == 422
    nulled = me.patch(url, json={"name": None})
    assert nulled.status_code == 422
    assert nulled.json()["error"]["code"] == "field_required"


def test_inn_is_locked_after_approval(platform_admin, clinic) -> None:
    me = clinic["client"]
    assert me.patch(f"{API_V1}/clinics/me", json={"inn": INN_LEGAL_2}).status_code == 200
    approve(platform_admin, clinic["id"])

    locked = me.patch(f"{API_V1}/clinics/me", json={"inn": INN_LEGAL})
    same = me.patch(f"{API_V1}/clinics/me", json={"inn": INN_LEGAL_2, "name": "Новое имя"})

    assert locked.status_code == 409
    assert locked.json()["error"]["code"] == "inn_locked"
    assert same.status_code == 200, same.text


def test_profile_update_cannot_duplicate_another_clinic(new_clinic) -> None:
    first = new_clinic()
    second = new_clinic(admin_email="second@example.com", address="г. Москва, ул. Арбат, д. 5")

    response = second["client"].patch(
        f"{API_V1}/clinics/me", json={"address": first["body"]["clinic"]["address"].upper()}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "clinic_exists"


def test_staff_cannot_edit_profile(client_factory, approved_clinic) -> None:
    doctor = staff_client(client_factory, approved_clinic, "doctor@aibolit.example")

    response = doctor.patch(f"{API_V1}/clinics/me", json={"name": "Взлом"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "role_required"


# --- Документы ------------------------------------------------------------------------


def test_upload_list_and_download_document(clinic) -> None:
    me = clinic["client"]

    created = upload(me, PDF, "clinic license.pdf", title="Лицензия")

    assert created.status_code == 201, created.text
    document = created.json()
    assert document["title"] == "Лицензия"
    assert document["content_type"] == "application/pdf"
    assert document["size_bytes"] == len(PDF)
    assert document["filename"] == "clinic license.pdf"
    assert "content" not in document

    listing = me.get(f"{API_V1}/clinics/me/documents")
    assert [item["id"] for item in listing.json()] == [document["id"]]

    downloaded = me.get(f"{API_V1}/clinics/me/documents/{document['id']}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == PDF
    assert downloaded.headers["content-type"] == "application/pdf"
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    assert downloaded.headers["cache-control"] == "private, no-store"
    assert "attachment" in downloaded.headers["content-disposition"]


def test_document_type_is_detected_by_content_not_by_name(clinic) -> None:
    disguised = upload(clinic["client"], PDF, "../../etc/evil.exe")
    image = upload(clinic["client"], PNG, "scan")

    assert disguised.status_code == 201, disguised.text
    assert disguised.json()["filename"] == "evil.pdf"
    assert disguised.json()["content_type"] == "application/pdf"
    assert image.json()["filename"] == "scan.png"
    assert image.json()["content_type"] == "image/png"


@pytest.mark.parametrize(
    ("content", "code", "http_status"),
    [
        (b"MZ\x90\x00 not a document", "document_type_unsupported", 422),
        (b"<html><script>alert(1)</script></html>", "document_type_unsupported", 422),
        (b"", "document_empty", 422),
        (b"%PDF-" + b"0" * MAX_DOCUMENT_BYTES, "document_too_large", 413),
    ],
)
def test_upload_rejects_bad_files(clinic, content: bytes, code: str, http_status: int) -> None:
    response = upload(clinic["client"], content)

    assert response.status_code == http_status
    assert response.json()["error"]["code"] == code
    assert clinic["client"].get(f"{API_V1}/clinics/me/documents").json() == []


def test_document_limit(clinic) -> None:
    for _ in range(MAX_DOCUMENTS_PER_CLINIC):
        assert upload(clinic["client"]).status_code == 201

    response = upload(clinic["client"])

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "documents_limit"


def test_platform_admin_downloads_document_and_it_is_audited(platform_admin, clinic, db: Session) -> None:
    document = upload(clinic["client"]).json()

    response = platform_admin.get(f"{API_V1}/admin/clinics/{clinic['id']}/documents/{document['id']}/download")

    assert response.status_code == 200
    assert response.content == PDF
    assert "clinic.document.downloaded" in audit_actions(db)
    # Документ другой клиники по этому адресу не отдаётся.
    assert platform_admin.get(f"{API_V1}/admin/clinics/9999/documents/{document['id']}/download").status_code == 404


def test_documents_of_one_clinic_are_hidden_from_another(new_clinic, client_factory) -> None:
    first = new_clinic()
    second = new_clinic(inn=INN_LEGAL_2, admin_email="second@example.com")
    owner = client_factory()
    register_owner(owner, email="owner@example.com")
    document = upload(first["client"]).json()
    path = f"{API_V1}/clinics/me/documents/{document['id']}"

    assert second["client"].get(f"{path}/download").status_code == 404
    assert second["client"].delete(path).status_code == 404
    assert second["client"].get(f"{API_V1}/clinics/me/documents").json() == []
    assert owner.get(f"{path}/download").status_code == 403


def test_document_can_be_deleted_only_while_under_review(platform_admin, clinic, db: Session) -> None:
    me = clinic["client"]
    first = upload(me).json()
    second = upload(me).json()

    assert me.delete(f"{API_V1}/clinics/me/documents/{first['id']}").status_code == 204
    assert "clinic.document.deleted" in audit_actions(db)

    approve(platform_admin, clinic["id"])
    locked = me.delete(f"{API_V1}/clinics/me/documents/{second['id']}")
    assert locked.status_code == 409
    assert locked.json()["error"]["code"] == "documents_locked"


def test_staff_cannot_upload_documents(client_factory, approved_clinic) -> None:
    doctor = staff_client(client_factory, approved_clinic, "doctor@aibolit.example")

    assert upload(doctor).status_code == 403


# --- Сотрудники -----------------------------------------------------------------------


def test_admin_invites_staff_who_sets_own_password(
    client_factory, approved_clinic, db: Session, clinic_mailbox: FakeEmailSender
) -> None:
    created = invite(approved_clinic["client"], email="Doctor@Aibolit.example", role="clinic_doctor")

    assert created.status_code == 201, created.text
    member = created.json()
    assert member["email"] == "doctor@aibolit.example"
    assert member["role"] == ROLE_CLINIC_DOCTOR
    assert member["status"] == "active"
    user = db.get(User, member["user_id"])
    assert user.role == ROLE_CLINIC_DOCTOR
    assert user.password_hash is None
    assert clinic_mailbox.messages[-1]["to"] == "doctor@aibolit.example"
    assert "Врач" in clinic_mailbox.messages[-1]["text"]
    assert "clinic.staff.invited" in audit_actions(db)

    # Пароль сотрудник задаёт сам: код приходит на почту, вход по паролю открывается.
    client = client_factory()
    code = request_reset_code(client, "doctor@aibolit.example")
    result = confirm_password_reset(client, "doctor@aibolit.example", code, STAFF_PASSWORD)
    assert result["status_code"] == 200
    assert result["body"]["user"]["role"] == ROLE_CLINIC_DOCTOR
    assert login(client_factory(), "doctor@aibolit.example", STAFF_PASSWORD)["status_code"] == 200


def test_staff_must_accept_consents_before_working(client_factory, approved_clinic) -> None:
    doctor = staff_client(client_factory, approved_clinic, "doctor@aibolit.example")

    assert doctor.get(f"{API_V1}/clinics/me").status_code == 200
    blocked = doctor.get(f"{API_V1}/clinics/me/staff")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "consent_required"

    accept_consents(doctor)

    allowed = doctor.get(f"{API_V1}/clinics/me/staff")
    assert allowed.status_code == 200
    assert {member["email"] for member in allowed.json()} == {"admin@aibolit.example", "doctor@aibolit.example"}


def test_doctor_and_registrar_cannot_manage_staff(client_factory, approved_clinic) -> None:
    doctor = staff_client(client_factory, approved_clinic, "doctor@aibolit.example")
    registrar = staff_client(client_factory, approved_clinic, "reg@aibolit.example", role="clinic_registrar")
    accept_consents(doctor)
    accept_consents(registrar)
    target = approved_clinic["client"].get(f"{API_V1}/clinics/me/staff").json()[0]

    for caller in (doctor, registrar):
        denied = invite(caller, email="third@aibolit.example")
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "role_required"
        assert caller.patch(f"{API_V1}/clinics/me/staff/{target['id']}", json={"status": "disabled"}).status_code == 403


def test_invite_rejects_taken_email_and_bad_role(approved_clinic, client_factory) -> None:
    me = approved_clinic["client"]
    owner = client_factory()
    register_owner(owner, email="owner@example.com")

    taken = invite(me, email="owner@example.com")
    own = invite(me, email="admin@aibolit.example")
    bad_role = invite(me, email="x@example.com", role="platform_admin")
    invite(me, email="doctor@aibolit.example")
    repeated = invite(me, email="doctor@aibolit.example")

    assert taken.status_code == 409
    assert own.status_code == 409
    assert bad_role.status_code == 422
    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "email_taken"


def test_admin_changes_staff_role(approved_clinic, db: Session) -> None:
    me = approved_clinic["client"]
    member = invite(me).json()

    response = me.patch(f"{API_V1}/clinics/me/staff/{member['id']}", json={"role": "clinic_registrar"})

    assert response.status_code == 200, response.text
    assert response.json()["role"] == "clinic_registrar"
    assert db.get(User, member["user_id"]).role == "clinic_registrar"
    assert "clinic.staff.updated" in audit_actions(db)


def test_disabled_staff_loses_access_immediately_and_can_be_restored(client_factory, approved_clinic) -> None:
    me = approved_clinic["client"]
    doctor = staff_client(client_factory, approved_clinic, "doctor@aibolit.example")
    member = next(m for m in me.get(f"{API_V1}/clinics/me/staff").json() if m["email"] == "doctor@aibolit.example")
    assert doctor.get(f"{API_V1}/clinics/me").status_code == 200
    refresh_token = login(client_factory(), "doctor@aibolit.example", STAFF_PASSWORD)["body"]["refresh_token"]

    disabled = me.patch(f"{API_V1}/clinics/me/staff/{member['id']}", json={"status": "disabled"})

    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["status"] == "disabled"
    assert doctor.get(f"{API_V1}/clinics/me").status_code == 401
    assert login(client_factory(), "doctor@aibolit.example", STAFF_PASSWORD)["status_code"] == 401
    refreshed = client_factory().post(f"{API_V1}/auth/refresh", json={"refresh_token": refresh_token})
    assert refreshed.status_code == 401

    restored = me.patch(f"{API_V1}/clinics/me/staff/{member['id']}", json={"status": "active"})

    assert restored.status_code == 200, restored.text
    assert login(client_factory(), "doctor@aibolit.example", STAFF_PASSWORD)["status_code"] == 200


def test_admin_cannot_modify_self(approved_clinic) -> None:
    me = approved_clinic["client"]
    own = me.get(f"{API_V1}/clinics/me").json()["my_staff_id"]

    response = me.patch(f"{API_V1}/clinics/me/staff/{own}", json={"status": "disabled"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "cannot_modify_self"


def test_staff_update_validation(approved_clinic) -> None:
    me = approved_clinic["client"]
    member = invite(me).json()
    url = f"{API_V1}/clinics/me/staff/{member['id']}"

    assert me.patch(url, json={}).status_code == 422
    assert me.patch(url, json={"role": "platform_admin"}).status_code == 422
    assert me.patch(url, json={"status": "banned"}).status_code == 422
    nothing = me.patch(url, json={"role": None})
    assert nothing.status_code == 422
    assert nothing.json()["error"]["code"] == "nothing_to_change"


def test_staff_of_another_clinic_is_not_accessible(new_clinic, platform_admin) -> None:
    first = new_clinic()
    second = new_clinic(inn=INN_LEGAL_2, admin_email="second@example.com")
    approve(platform_admin, first["id"])
    approve(platform_admin, second["id"])
    foreign = invite(first["client"]).json()

    patched = second["client"].patch(f"{API_V1}/clinics/me/staff/{foreign['id']}", json={"status": "disabled"})
    listing = second["client"].get(f"{API_V1}/clinics/me/staff").json()

    assert patched.status_code == 404
    assert [member["email"] for member in listing] == ["second@example.com"]


def test_staff_list_is_paginated(approved_clinic) -> None:
    me = approved_clinic["client"]
    for index in range(3):
        assert invite(me, email=f"doctor{index}@aibolit.example").status_code == 201

    response = me.get(f"{API_V1}/clinics/me/staff", params={"limit": 2, "offset": 1})

    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "4"
    assert len(response.json()) == 2
