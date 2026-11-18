"""Кабинет врача: приём, записи в медкарту, правка с историей, вложения, права и изоляция."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import (
    ROLE_PLATFORM_ADMIN,
    AuditLog,
    Encounter,
    MedicalRecord,
    RecordAttachment,
    User,
)
from app.services.clinics import MAX_DOCUMENT_BYTES
from tests.helpers import API_V1, register_owner
from tests.test_clinics import (
    INN_LEGAL_2,
    PDF,
    PNG,
    accept_consents,
    approve,
    as_user,
    clinic_payload,
    staff_client,
)
from tests.test_patient_access import open_by_code, suspend

CLINIC_NAME = "Ветклиника «Айболит»"
ADMIN_NAME = "Иванова Мария Сергеевна"


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
    def make(email="owner@example.com", phone="8 999 111-22-33", pet_name="Барсик") -> dict:
        client = client_factory()
        register_owner(client, email=email)
        assert client.put(f"{API_V1}/profile/phone", json={"phone": phone}).status_code == 200
        created = client.post(
            f"{API_V1}/pets",
            json={"name": pet_name, "species": "dog", "birth_date": "2020-03-01", "sex": "male"},
        )
        assert created.status_code == 201, created.text
        return {"client": client, "pet": created.json(), "id": created.json()["id"]}

    return make


@pytest.fixture()
def visit(make_owner, approved_clinic) -> dict:
    """Клиника с открытым доступом к питомцу и уже начатым приёмом."""
    owner = make_owner()
    opened = open_by_code(owner, approved_clinic)
    encounter = start(approved_clinic, owner["id"])
    assert encounter.status_code == 201, encounter.text
    return {
        "owner": owner,
        "clinic": approved_clinic,
        "client": approved_clinic["client"],
        "grant_id": opened["grant_id"],
        "encounter": encounter.json(),
    }


def start(clinic: dict, pet_id: int):
    return clinic["client"].post(f"{API_V1}/clinics/me/patients/{pet_id}/encounters")


def finish(client: TestClient, encounter_id: int):
    return client.post(f"{API_V1}/clinics/me/encounters/{encounter_id}/finish")


def add_clinic_record(client: TestClient, encounter_id: int, **overrides):
    payload = {"kind": "visit", "title": "Плановый осмотр", "description": "Жалоб нет", "diagnosis": "Здоров"}
    payload.update(overrides)
    return client.post(f"{API_V1}/clinics/me/encounters/{encounter_id}/records", json=payload)


def edit_record(client: TestClient, record_id: int, **payload):
    return client.patch(f"{API_V1}/clinics/me/records/{record_id}", json=payload)


def attach(client: TestClient, record_id: int, content: bytes = PDF, filename: str = "blood test.pdf"):
    return client.post(
        f"{API_V1}/clinics/me/records/{record_id}/attachments",
        files={"file": (filename, content, "application/octet-stream")},
    )


def owner_record(owner: dict, kind: str = "visit", title: str = "Запись владельца") -> int:
    response = owner["client"].post(
        f"{API_V1}/pets/{owner['id']}/records",
        json={"kind": kind, "title": title, "occurred_at": "2026-01-10T10:00:00Z"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def revoke_access(visit_: dict) -> None:
    response = visit_["owner"]["client"].post(f"{API_V1}/access-grants/{visit_['grant_id']}/revoke")
    assert response.status_code == 200, response.text


def audit_actions(db: Session) -> list[str]:
    return [row.action for row in db.scalars(select(AuditLog)).all()]


def doctor_client(client_factory, approved: dict, email: str = "doctor@aibolit.example") -> TestClient:
    client = staff_client(client_factory, approved, email, role="clinic_doctor")
    accept_consents(client)
    return client


# --- Начало приёма ------------------------------------------------------------------------


def test_doctor_starts_encounter_for_patient_with_access(make_owner, approved_clinic, db: Session) -> None:
    owner = make_owner()
    open_by_code(owner, approved_clinic)

    response = start(approved_clinic, owner["id"])

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["pet"]["id"] == owner["id"]
    assert body["pet"]["name"] == "Барсик"
    assert body["doctor_name"] == ADMIN_NAME
    assert body["finished_at"] is None
    assert body["duration_seconds"] is None
    assert body["records_count"] == 0
    assert body["records"] == []
    assert "encounter.started" in audit_actions(db)


def test_encounter_needs_active_access_to_the_patient(make_owner, approved_clinic, second_clinic) -> None:
    owner = make_owner()
    assert start(approved_clinic, owner["id"]).status_code == 404

    opened = open_by_code(owner, approved_clinic)
    assert start(second_clinic, owner["id"]).status_code == 404
    assert start(approved_clinic, 999999).status_code == 404

    owner["client"].post(f"{API_V1}/access-grants/{opened['grant_id']}/revoke")
    assert start(approved_clinic, owner["id"]).status_code == 404


def test_only_one_open_encounter_per_patient(visit) -> None:
    again = start(visit["clinic"], visit["owner"]["id"])

    assert again.status_code == 409
    error = again.json()["error"]
    assert error["code"] == "encounter_in_progress"
    assert error["details"]["encounter_id"] == visit["encounter"]["id"]

    assert finish(visit["client"], visit["encounter"]["id"]).status_code == 200
    assert start(visit["clinic"], visit["owner"]["id"]).status_code == 201


def test_registrar_cannot_run_encounters(visit, client_factory) -> None:
    registrar = staff_client(client_factory, visit["clinic"], "reg@aibolit.example", role="clinic_registrar")
    accept_consents(registrar)
    base = f"{API_V1}/clinics/me"
    encounter_id = visit["encounter"]["id"]

    for response in (
        registrar.post(f"{base}/patients/{visit['owner']['id']}/encounters"),
        registrar.get(f"{base}/encounters"),
        registrar.get(f"{base}/encounters/{encounter_id}"),
        registrar.post(f"{base}/encounters/{encounter_id}/finish"),
        registrar.post(f"{base}/encounters/{encounter_id}/records", json={"title": "x"}),
    ):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "role_required"


def test_owner_and_pending_or_suspended_clinic_are_blocked(
    make_owner, new_clinic, approved_clinic, platform_admin
) -> None:
    owner = make_owner()
    open_by_code(owner, approved_clinic)
    pending = new_clinic(inn=INN_LEGAL_2, admin_email="pending@example.com")

    by_owner = owner["client"].post(f"{API_V1}/clinics/me/patients/{owner['id']}/encounters")
    by_pending = start(pending, owner["id"])
    suspend(platform_admin, approved_clinic["id"])
    by_suspended = start(approved_clinic, owner["id"])

    assert by_owner.status_code == 403
    assert by_owner.json()["error"]["code"] == "not_clinic_staff"
    assert by_pending.json()["error"]["code"] == "clinic_not_approved"
    assert by_suspended.json()["error"]["code"] == "clinic_not_approved"


# --- Завершение и список приёмов ------------------------------------------------------------


def test_finish_fixes_time_and_cannot_repeat(visit, db: Session) -> None:
    response = finish(visit["client"], visit["encounter"]["id"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["finished_at"] is not None
    assert isinstance(body["duration_seconds"], int)
    assert body["duration_seconds"] >= 0
    again = finish(visit["client"], visit["encounter"]["id"])
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "invalid_status"
    assert again.json()["error"]["details"]["current"] == "completed"
    assert {"encounter.started", "encounter.finished"} <= set(audit_actions(db))


def test_only_the_encounters_doctor_or_admin_can_finish_it(make_owner, approved_clinic, client_factory) -> None:
    owner = make_owner()
    open_by_code(owner, approved_clinic)
    first = doctor_client(client_factory, approved_clinic, "doctor1@aibolit.example")
    second = doctor_client(client_factory, approved_clinic, "doctor2@aibolit.example")
    encounter_id = start({"client": first}, owner["id"]).json()["id"]

    stranger = finish(second, encounter_id)
    by_admin = finish(approved_clinic["client"], encounter_id)

    assert stranger.status_code == 403
    assert stranger.json()["error"]["code"] == "not_your_encounter"
    assert by_admin.status_code == 200


def test_encounter_list_filters_counts_and_pagination(make_owner, approved_clinic, client_factory) -> None:
    first_owner = make_owner()
    second_owner = make_owner(email="owner2@example.com", phone="+7 999 222-33-44", pet_name="Мурка")
    open_by_code(first_owner, approved_clinic)
    open_by_code(second_owner, approved_clinic)
    admin = approved_clinic["client"]
    first_id = start(approved_clinic, first_owner["id"]).json()["id"]
    second_id = start(approved_clinic, second_owner["id"]).json()["id"]
    add_clinic_record(admin, second_id)
    add_clinic_record(admin, second_id, kind="lab", title="Анализ крови")
    finish(admin, first_id)
    base = f"{API_V1}/clinics/me/encounters"

    everything = admin.get(base)
    open_only = admin.get(base, params={"status": "in_progress"})
    done_only = admin.get(base, params={"status": "completed"})
    by_pet = admin.get(base, params={"pet_id": first_owner["id"]})
    page = admin.get(base, params={"limit": 1, "offset": 1})
    other_doctor = doctor_client(client_factory, approved_clinic)

    assert everything.headers["X-Total-Count"] == "2"
    assert [item["id"] for item in everything.json()] == [second_id, first_id]  # свежие сверху
    assert everything.json()[0]["records_count"] == 2
    assert [item["id"] for item in open_only.json()] == [second_id]
    assert [item["id"] for item in done_only.json()] == [first_id]
    assert [item["id"] for item in by_pet.json()] == [first_id]
    assert [item["id"] for item in page.json()] == [first_id]
    assert len(admin.get(base, params={"mine": "true"}).json()) == 2
    assert other_doctor.get(base, params={"mine": "true"}).json() == []
    assert len(other_doctor.get(base).json()) == 2


def test_encounters_are_isolated_between_clinics(visit, second_clinic) -> None:
    other = second_clinic["client"]
    base = f"{API_V1}/clinics/me/encounters/{visit['encounter']['id']}"

    assert other.get(base).status_code == 404
    assert other.post(f"{base}/finish").status_code == 404
    assert add_clinic_record(other, visit["encounter"]["id"]).status_code == 404
    assert other.get(f"{API_V1}/clinics/me/encounters").json() == []


def test_encounter_detail_follows_the_owners_access(visit) -> None:
    client, owner, encounter_id = visit["client"], visit["owner"], visit["encounter"]["id"]
    add_clinic_record(client, encounter_id, title="Осмотр")
    add_clinic_record(client, encounter_id, kind="vaccination", title="Бешенство")
    url = f"{API_V1}/clinics/me/encounters/{encounter_id}"

    full = client.get(url).json()
    assert {item["title"] for item in full["records"]} == {"Осмотр", "Бешенство"}
    assert full["records_count"] == 2

    revoke_access(visit)
    closed = client.get(url)
    assert closed.status_code == 403
    assert closed.json()["error"]["code"] == "access_required"
    assert client.get(f"{API_V1}/clinics/me/encounters").status_code == 200  # список без медданных

    # Новый доступ только к прививкам: чужие разделы в приёме скрыты.
    open_by_code(owner, visit["clinic"], scopes=["vaccinations"])
    narrowed = client.get(url).json()
    assert [item["title"] for item in narrowed["records"]] == ["Бешенство"]
    assert narrowed["records_count"] == 1


# --- Записи врача -----------------------------------------------------------------------------


def test_doctors_record_reaches_the_owner_immediately(visit, db: Session) -> None:
    owner, client = visit["owner"], visit["client"]

    created = add_clinic_record(
        client, visit["encounter"]["id"], title="Осмотр", description="Кашель", diagnosis="ОРВИ"
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["author_type"] == "clinic"
    assert body["author_name"] == ADMIN_NAME
    assert body["clinic_name"] == CLINIC_NAME
    assert body["encounter_id"] == visit["encounter"]["id"]
    assert body["attachments"] == []

    records = owner["client"].get(f"{API_V1}/pets/{owner['id']}/records").json()
    assert len(records) == 1
    assert records[0]["id"] == body["id"]
    assert records[0]["author_type"] == "clinic"
    assert records[0]["source"] == "manual"
    assert records[0]["clinic_name"] == CLINIC_NAME
    assert records[0]["diagnosis"] == "ОРВИ"
    assert records[0]["description"] == "Кашель"

    revisions = owner["client"].get(f"{API_V1}/records/{body['id']}/revisions").json()
    assert [item["action"] for item in revisions] == ["created"]
    assert revisions[0]["changed_by_id"] == visit["clinic"]["body"]["user"]["id"]
    card = client.get(f"{API_V1}/clinics/me/patients/{owner['id']}").json()
    assert [item["title"] for item in card["records"]] == ["Осмотр"]
    assert "clinic_record.created" in audit_actions(db)


def test_all_record_kinds_can_be_written(visit) -> None:
    client, encounter_id = visit["client"], visit["encounter"]["id"]

    for kind in ("visit", "lab", "prescription", "vaccination", "other"):
        response = add_clinic_record(client, encounter_id, kind=kind, title=f"Запись {kind}")
        assert response.status_code == 201, (kind, response.text)

    card = client.get(f"{API_V1}/clinics/me/patients/{visit['owner']['id']}").json()
    assert len(card["records"]) == 5
    assert [item["title"] for item in card["vaccinations"]] == ["Запись vaccination"]


def test_clinic_name_and_author_come_from_the_server(visit) -> None:
    created = add_clinic_record(
        visit["client"],
        visit["encounter"]["id"],
        clinic_name="Чужая клиника",
        author_type="owner",
        author_user_id=1,
        source="mis",
    )

    assert created.status_code == 201
    body = created.json()
    assert body["clinic_name"] == CLINIC_NAME
    assert body["author_type"] == "clinic"
    records = visit["owner"]["client"].get(f"{API_V1}/pets/{visit['owner']['id']}/records").json()
    assert records[0]["source"] == "manual"


def test_writing_needs_the_matching_section_of_the_card(make_owner, approved_clinic) -> None:
    profile_only = make_owner()
    vaccinations_only = make_owner(email="owner2@example.com", phone="+7 999 222-33-44", pet_name="Мурка")
    open_by_code(profile_only, approved_clinic, scopes=["profile"])
    open_by_code(vaccinations_only, approved_clinic, scopes=["vaccinations"])
    client = approved_clinic["client"]
    first = start(approved_clinic, profile_only["id"]).json()["id"]
    second = start(approved_clinic, vaccinations_only["id"]).json()["id"]

    denied = add_clinic_record(client, first)
    visit_denied = add_clinic_record(client, second)
    vaccination_ok = add_clinic_record(client, second, kind="vaccination", title="Бешенство")

    assert denied.status_code == 403
    error = denied.json()["error"]
    assert error["code"] == "scope_required"
    assert error["details"]["kind"] == "visit"
    assert error["details"]["required"] == ["records"]
    assert visit_denied.status_code == 403
    assert vaccination_ok.status_code == 201, vaccination_ok.text


def test_record_payload_validation(visit) -> None:
    client, encounter_id = visit["client"], visit["encounter"]["id"]
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

    for overrides in (
        {"title": ""},
        {"title": "   "},
        {"kind": "surgery"},
        {"description": "x" * 8001},
        {"diagnosis": "x" * 4001},
    ):
        assert add_clinic_record(client, encounter_id, **overrides).status_code == 422, overrides

    in_future = add_clinic_record(client, encounter_id, occurred_at=future)
    assert in_future.status_code == 422
    assert in_future.json()["error"]["code"] == "occurred_in_future"


def test_record_time_defaults_to_now_and_accepts_past_and_naive_values(visit) -> None:
    client, encounter_id = visit["client"], visit["encounter"]["id"]

    default = add_clinic_record(client, encounter_id).json()
    past = add_clinic_record(client, encounter_id, occurred_at="2026-01-10T10:00:00Z").json()
    naive = add_clinic_record(client, encounter_id, occurred_at="2026-01-11T09:30:00")

    assert abs(datetime.fromisoformat(default["occurred_at"]) - datetime.now(UTC)) < timedelta(minutes=1)
    assert datetime.fromisoformat(past["occurred_at"]).date().isoformat() == "2026-01-10"
    assert naive.status_code == 201, naive.text


def test_closed_encounter_accepts_no_new_records(visit) -> None:
    finish(visit["client"], visit["encounter"]["id"])

    response = add_clinic_record(visit["client"], visit["encounter"]["id"])

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "encounter_closed"


def test_revoked_access_stops_writing_at_once(visit) -> None:
    revoke_access(visit)

    response = add_clinic_record(visit["client"], visit["encounter"]["id"])

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "access_required"


# --- Правка своих записей ---------------------------------------------------------------------


def test_doctor_edits_own_record_and_history_is_kept(visit, db: Session) -> None:
    owner, client = visit["owner"], visit["client"]
    record = add_clinic_record(client, visit["encounter"]["id"], title="Осмотр", diagnosis="ОРВИ").json()

    patched = edit_record(client, record["id"], diagnosis="Бронхит", title="Осмотр (уточнено)")

    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["diagnosis"] == "Бронхит"
    assert body["title"] == "Осмотр (уточнено)"
    records = owner["client"].get(f"{API_V1}/pets/{owner['id']}/records").json()
    assert records[0]["diagnosis"] == "Бронхит"

    revisions = owner["client"].get(f"{API_V1}/records/{record['id']}/revisions").json()
    assert [item["action"] for item in revisions] == ["updated", "created"]
    assert revisions[0]["changed_by_id"] == visit["clinic"]["body"]["user"]["id"]
    before = owner["client"].get(f"{API_V1}/records/{record['id']}/revisions/{revisions[0]['id']}").json()
    assert before["before"]["diagnosis"] == "ОРВИ"
    assert before["before"]["title"] == "Осмотр"
    assert "clinic_record.updated" in audit_actions(db)


def test_record_can_be_corrected_after_the_encounter_is_finished(visit) -> None:
    record = add_clinic_record(visit["client"], visit["encounter"]["id"]).json()
    finish(visit["client"], visit["encounter"]["id"])

    response = edit_record(visit["client"], record["id"], description="Дополнено после приёма")

    assert response.status_code == 200
    assert response.json()["description"] == "Дополнено после приёма"


def test_record_edit_validation(visit) -> None:
    client = visit["client"]
    record = add_clinic_record(client, visit["encounter"]["id"], kind="lab").json()
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

    assert edit_record(client, record["id"]).status_code == 422
    nulled_title = edit_record(client, record["id"], title=None)
    assert nulled_title.status_code == 422
    assert nulled_title.json()["error"]["code"] == "field_required"
    assert edit_record(client, record["id"], occurred_at=None).status_code == 422
    assert edit_record(client, record["id"], occurred_at=future).status_code == 422
    assert edit_record(client, record["id"], diagnosis="x" * 4001).status_code == 422

    # Вид записи менять нельзя: лишнее поле игнорируется, вид остаётся прежним.
    response = edit_record(client, record["id"], kind="visit", title="Новое название")
    assert response.status_code == 200
    assert response.json()["kind"] == "lab"
    # Описание и диагноз можно очистить.
    cleared = edit_record(client, record["id"], description=None, diagnosis=None)
    assert cleared.json()["description"] is None
    assert cleared.json()["diagnosis"] is None


def test_clinic_edits_only_its_own_records(visit, make_owner, second_clinic) -> None:
    client, owner = visit["client"], visit["owner"]
    own_by_owner = owner_record(owner)
    # Вторая клиника тоже получила доступ и написала свою запись.
    open_by_code(owner, second_clinic)
    other_encounter = start(second_clinic, owner["id"]).json()["id"]
    other_record = add_clinic_record(second_clinic["client"], other_encounter, title="Запись второй клиники").json()
    stranger = make_owner(email="owner2@example.com", phone="+7 999 222-33-44", pet_name="Мурка")
    invisible = owner_record(stranger)

    by_owner = edit_record(client, own_by_owner, title="Подмена")
    by_other_clinic = edit_record(client, other_record["id"], title="Подмена")
    no_access = edit_record(client, invisible, title="Подмена")

    assert by_owner.status_code == 403
    assert by_owner.json()["error"]["code"] == "record_not_editable"
    assert by_other_clinic.status_code == 403
    assert no_access.status_code == 404
    assert edit_record(second_clinic["client"], other_record["id"], title="Моя правка").status_code == 200


def test_edit_follows_the_owners_access(visit) -> None:
    record = add_clinic_record(visit["client"], visit["encounter"]["id"]).json()
    revoke_access(visit)

    assert edit_record(visit["client"], record["id"], title="После отзыва").status_code == 404


def test_clinic_cannot_delete_records(visit) -> None:
    record = add_clinic_record(visit["client"], visit["encounter"]["id"]).json()

    response = visit["client"].delete(f"{API_V1}/clinics/me/records/{record['id']}")

    assert response.status_code == 405
    assert visit["owner"]["client"].get(f"{API_V1}/records/{record['id']}").status_code == 200


# --- Вложения ------------------------------------------------------------------------------------


@pytest.fixture()
def record_with_file(visit) -> dict:
    record = add_clinic_record(visit["client"], visit["encounter"]["id"], kind="lab", title="Анализ крови").json()
    uploaded = attach(visit["client"], record["id"])
    assert uploaded.status_code == 201, uploaded.text
    return {**visit, "record": record, "attachment": uploaded.json()}


def test_doctor_uploads_lists_and_downloads_a_file(record_with_file) -> None:
    client, record, attachment = record_with_file["client"], record_with_file["record"], record_with_file["attachment"]

    assert attachment["filename"] == "blood test.pdf"
    assert attachment["content_type"] == "application/pdf"
    assert attachment["size_bytes"] == len(PDF)
    assert "content" not in attachment

    listing = client.get(f"{API_V1}/clinics/me/records/{record['id']}/attachments").json()
    assert [item["id"] for item in listing] == [attachment["id"]]
    downloaded = client.get(f"{API_V1}/clinics/me/records/{record['id']}/attachments/{attachment['id']}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == PDF
    assert downloaded.headers["content-type"] == "application/pdf"
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    assert downloaded.headers["cache-control"] == "private, no-store"
    detail = client.get(f"{API_V1}/clinics/me/encounters/{record_with_file['encounter']['id']}").json()
    assert [item["id"] for item in detail["records"][0]["attachments"]] == [attachment["id"]]


def test_owner_sees_and_downloads_the_doctors_file(record_with_file) -> None:
    owner, record, attachment = record_with_file["owner"], record_with_file["record"], record_with_file["attachment"]

    listing = owner["client"].get(f"{API_V1}/records/{record['id']}/attachments")
    downloaded = owner["client"].get(f"{API_V1}/records/{record['id']}/attachments/{attachment['id']}/download")

    assert [item["id"] for item in listing.json()] == [attachment["id"]]
    assert downloaded.status_code == 200
    assert downloaded.content == PDF


def test_file_type_comes_from_content_not_from_name(visit) -> None:
    record = add_clinic_record(visit["client"], visit["encounter"]["id"]).json()

    response = attach(visit["client"], record["id"], PNG, "../../scan.exe")

    assert response.status_code == 201, response.text
    assert response.json()["filename"] == "scan.png"
    assert response.json()["content_type"] == "image/png"


def test_file_is_encrypted_at_rest(record_with_file, db: Session) -> None:
    raw = db.execute(text("SELECT content FROM record_attachments")).scalar_one()
    stored = bytes(raw)

    assert stored.startswith(b"enc:v1:")
    assert b"%PDF" not in stored
    assert PDF not in stored


@pytest.mark.parametrize(
    ("content", "code", "http_status"),
    [
        (b"MZ\x90\x00 not a document", "document_type_unsupported", 422),
        (b"", "document_empty", 422),
        (b"%PDF-" + b"0" * MAX_DOCUMENT_BYTES, "document_too_large", 413),
    ],
)
def test_bad_files_are_rejected(visit, content: bytes, code: str, http_status: int) -> None:
    record = add_clinic_record(visit["client"], visit["encounter"]["id"]).json()

    response = attach(visit["client"], record["id"], content)

    assert response.status_code == http_status
    assert response.json()["error"]["code"] == code
    assert visit["client"].get(f"{API_V1}/clinics/me/records/{record['id']}/attachments").json() == []


def test_attachment_limit_per_record(visit, monkeypatch) -> None:
    monkeypatch.setattr("app.api.encounters.MAX_ATTACHMENTS_PER_RECORD", 2)
    record = add_clinic_record(visit["client"], visit["encounter"]["id"]).json()

    assert attach(visit["client"], record["id"]).status_code == 201
    assert attach(visit["client"], record["id"]).status_code == 201
    limited = attach(visit["client"], record["id"])

    assert limited.status_code == 409
    assert limited.json()["error"]["code"] == "attachments_limit"


def test_clinic_reads_but_cannot_attach_to_a_foreign_record(visit, second_clinic) -> None:
    owner = visit["owner"]
    open_by_code(owner, second_clinic)
    other_encounter = start(second_clinic, owner["id"]).json()["id"]
    other_record = add_clinic_record(second_clinic["client"], other_encounter, kind="lab").json()
    other_file = attach(second_clinic["client"], other_record["id"]).json()
    first = visit["client"]
    base = f"{API_V1}/clinics/me/records/{other_record['id']}/attachments"

    listing = first.get(base)
    downloaded = first.get(f"{base}/{other_file['id']}/download")
    upload = attach(first, other_record["id"])

    assert [item["id"] for item in listing.json()] == [other_file["id"]]
    assert downloaded.content == PDF
    assert upload.status_code == 403
    assert upload.json()["error"]["code"] == "record_not_editable"


def test_file_access_follows_the_owners_grant(record_with_file) -> None:
    client, owner = record_with_file["client"], record_with_file["owner"]
    record_id, attachment_id = record_with_file["record"]["id"], record_with_file["attachment"]["id"]
    base = f"{API_V1}/clinics/me/records/{record_id}/attachments"

    revoke_access(record_with_file)
    assert client.get(base).status_code == 404
    assert client.get(f"{base}/{attachment_id}/download").status_code == 404

    # Новый доступ без раздела записей: файлы записи закрыты.
    open_by_code(owner, record_with_file["clinic"], scopes=["profile"])
    assert client.get(base).status_code == 404
    assert attach(client, record_id).status_code == 404


def test_file_downloads_and_uploads_are_audited(record_with_file, db: Session) -> None:
    record_id, attachment_id = record_with_file["record"]["id"], record_with_file["attachment"]["id"]

    record_with_file["client"].get(f"{API_V1}/clinics/me/records/{record_id}/attachments/{attachment_id}/download")

    actions = audit_actions(db)
    assert "record_attachment.uploaded" in actions
    assert actions.count("record_attachment.downloaded") == 1


def test_attachment_ids_are_checked_against_the_record(visit) -> None:
    client = visit["client"]
    first = add_clinic_record(client, visit["encounter"]["id"], title="Первая").json()
    second = add_clinic_record(client, visit["encounter"]["id"], title="Вторая").json()
    attachment = attach(client, first["id"]).json()
    base = f"{API_V1}/clinics/me/records"

    assert client.get(f"{base}/{second['id']}/attachments/{attachment['id']}/download").status_code == 404
    assert client.get(f"{base}/{first['id']}/attachments/999999/download").status_code == 404
    assert client.get(f"{base}/999999/attachments").status_code == 404


def test_registrar_cannot_touch_files(record_with_file, client_factory) -> None:
    registrar = staff_client(client_factory, record_with_file["clinic"], "reg@aibolit.example", role="clinic_registrar")
    accept_consents(registrar)
    record_id = record_with_file["record"]["id"]

    assert registrar.get(f"{API_V1}/clinics/me/records/{record_id}/attachments").status_code == 403
    assert attach(registrar, record_id).status_code == 403


def test_owner_file_endpoints_are_scoped_to_the_owner(record_with_file, make_owner, db: Session) -> None:
    owner, record_id = record_with_file["owner"], record_with_file["record"]["id"]
    attachment_id = record_with_file["attachment"]["id"]
    stranger = make_owner(email="owner2@example.com", phone="+7 999 222-33-44", pet_name="Мурка")
    base = f"{API_V1}/records/{record_id}/attachments"

    assert stranger["client"].get(base).status_code == 404
    assert stranger["client"].get(f"{base}/{attachment_id}/download").status_code == 404
    assert stranger["client"].delete(f"{base}/{attachment_id}").status_code == 404

    assert owner["client"].delete(f"{base}/{attachment_id}").status_code == 204
    assert owner["client"].get(f"{base}/{attachment_id}/download").status_code == 404
    assert owner["client"].get(base).json() == []
    assert "record_attachment.deleted" in audit_actions(db)


# --- Каскады ----------------------------------------------------------------------------------------


def test_deleting_a_record_removes_its_files(record_with_file, db: Session) -> None:
    record_id = record_with_file["record"]["id"]

    deleted = record_with_file["owner"]["client"].delete(f"{API_V1}/records/{record_id}")

    assert deleted.status_code == 204
    db.expire_all()
    assert db.scalars(select(RecordAttachment).where(RecordAttachment.record_id == record_id)).all() == []


def test_deleting_a_pet_removes_encounters_records_and_files(record_with_file, db: Session) -> None:
    pet_id = record_with_file["owner"]["id"]

    deleted = record_with_file["owner"]["client"].delete(f"{API_V1}/pets/{pet_id}")

    assert deleted.status_code == 204
    db.expire_all()
    assert db.scalars(select(Encounter).where(Encounter.pet_id == pet_id)).all() == []
    assert db.scalars(select(MedicalRecord).where(MedicalRecord.pet_id == pet_id)).all() == []
    assert db.scalars(select(RecordAttachment)).all() == []
