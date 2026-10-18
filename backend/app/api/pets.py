from datetime import date
from pathlib import Path
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, get_owned_pet, require_consents
from app.api.pagination import PaginationParams, pagination_headers
from app.config import get_settings
from app.models import REQUIRED_CONSENTS, Pet
from app.schemas.pets import PetCreate, PetResponse, PetUpdate, PublicMedicalCard
from app.services.audit import ACTOR_ANONYMOUS, record_audit
from app.services.idempotency import IDEMPOTENCY_HEADER, replay_response, store_response

router = APIRouter(prefix="/pets", tags=["pets"])

ALLOWED_PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
ENDPOINT_CREATE = "POST /pets"


@router.get("", response_model=list[PetResponse])
def list_pets(user: CurrentUser, pagination: PaginationParams, response: Response, db: DbSession):
    """Только питомцы текущего владельца: чужой питомец не виден ни в одном списке."""
    total = db.scalar(select(func.count()).select_from(Pet).where(Pet.owner_id == user.id)) or 0
    rows = db.scalars(
        select(Pet)
        .where(Pet.owner_id == user.id)
        .order_by(Pet.id)
        .limit(pagination.limit)
        .offset(pagination.offset)
    ).all()
    pagination_headers(response, total=total, pagination=pagination)
    return list(rows)


@router.post(
    "",
    response_model=PetResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_consents(*REQUIRED_CONSENTS))],
)
def create_pet(payload: PetCreate, request: Request, user: CurrentUser, db: DbSession):
    idempotency_key = request.headers.get(IDEMPOTENCY_HEADER)
    payload_data = payload.model_dump(mode="json")
    if idempotency_key:
        replayed = replay_response(
            db, user_id=user.id, key=idempotency_key, endpoint=ENDPOINT_CREATE, payload=payload_data
        )
        if replayed is not None:
            return replayed

    pet = Pet(**payload.model_dump(), owner_id=user.id, medical_secret_token=token_urlsafe(32))
    db.add(pet)
    db.commit()
    db.refresh(pet)

    body = PetResponse.model_validate(pet).model_dump(mode="json")
    if idempotency_key:
        store_response(
            db,
            user_id=user.id,
            key=idempotency_key,
            endpoint=ENDPOINT_CREATE,
            payload=payload_data,
            status_code=status.HTTP_201_CREATED,
            body=body,
        )
    return body


@router.get("/public/medical-card/{token}", response_model=PublicMedicalCard)
def public_medical_card(token: str, request: Request, db: DbSession):
    """Публичная медкарта по длинному токену: без авторизации, без личных заметок владельца.

    Каждое обращение попадает в журнал доступа: это медицинские данные.
    """
    pet = db.scalar(select(Pet).where(Pet.medical_secret_token == token))
    if not pet:
        record_audit(
            db,
            action="medical_card.read",
            actor_type=ACTOR_ANONYMOUS,
            entity="pet",
            request=request,
            details={"result": "not_found"},
        )
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Medical card not found")

    record_audit(
        db,
        action="medical_card.read",
        actor_type=ACTOR_ANONYMOUS,
        entity="pet",
        entity_id=pet.id,
        request=request,
        details={"result": "ok"},
    )

    age_years = None
    if pet.birth_date:
        today = date.today()
        age_years = today.year - pet.birth_date.year - ((today.month, today.day) < (pet.birth_date.month, pet.birth_date.day))
    vaccinations = [
        {"title": event.title, "date": event.starts_at, "status": event.status}
        for event in pet.events
        if event.event_type in {"vaccine", "vaccination"}
    ]
    return {
        "id": pet.id, "name": pet.name, "species": pet.species, "breed": pet.breed,
        "birth_date": pet.birth_date, "sex": pet.sex, "weight_kg": pet.weight_kg, "height_cm": pet.height_cm,
        "photo_url": pet.photo_url, "age_years": age_years, "vaccinations": vaccinations,
    }


@router.get("/{pet_id}", response_model=PetResponse)
def get_pet(pet_id: int, user: CurrentUser, db: DbSession):
    return get_owned_pet(pet_id, user, db)


@router.patch("/{pet_id}", response_model=PetResponse)
def update_pet(pet_id: int, payload: PetUpdate, user: CurrentUser, db: DbSession):
    pet = get_owned_pet(pet_id, user, db)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(pet, key, value)
    db.commit()
    db.refresh(pet)
    return pet


@router.delete("/{pet_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pet(pet_id: int, request: Request, user: CurrentUser, db: DbSession):
    pet = get_owned_pet(pet_id, user, db)
    pet_id_value = pet.id
    db.delete(pet)
    db.commit()
    record_audit(
        db,
        action="pet.deleted",
        actor_user_id=user.id,
        entity="pet",
        entity_id=pet_id_value,
        request=request,
    )


@router.post("/{pet_id}/photo", response_model=PetResponse)
async def upload_photo(
    pet_id: int,
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
):
    pet = get_owned_pet(pet_id, user, db)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_PHOTO_SUFFIXES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only jpg, png and webp images are supported")
    directory = Path(get_settings().upload_dir)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{token_urlsafe(16)}{suffix}"
    (directory / filename).write_bytes(await file.read())
    pet.photo_url = f"/uploads/{filename}"
    db.commit()
    db.refresh(pet)
    return pet


@router.post("/{pet_id}/medical-token", response_model=PetResponse)
def renew_medical_token(pet_id: int, request: Request, user: CurrentUser, db: DbSession):
    pet = get_owned_pet(pet_id, user, db)
    pet.medical_secret_token = token_urlsafe(32)
    db.commit()
    db.refresh(pet)
    record_audit(
        db,
        action="medical_token.renewed",
        actor_user_id=user.id,
        entity="pet",
        entity_id=pet.id,
        request=request,
    )
    return pet
