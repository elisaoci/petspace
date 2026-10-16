from datetime import date
from pathlib import Path
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Pet
from app.schemas.pets import PetCreate, PetResponse, PetUpdate, PublicMedicalCard

router = APIRouter(prefix="/pets", tags=["pets"])

def _get(db: Session, pet_id: int) -> Pet:
    pet = db.get(Pet, pet_id)
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found")
    return pet

@router.get("", response_model=list[PetResponse])
def list_pets(db: Session = Depends(get_db)):
    return db.scalars(select(Pet).order_by(Pet.id)).all()

@router.post("", response_model=PetResponse, status_code=status.HTTP_201_CREATED)
def create_pet(payload: PetCreate, db: Session = Depends(get_db)):
    pet = Pet(**payload.model_dump(), medical_secret_token=token_urlsafe(32))
    db.add(pet); db.commit(); db.refresh(pet)
    return pet

@router.get("/public/medical-card/{token}", response_model=PublicMedicalCard)
def public_medical_card(token: str, db: Session = Depends(get_db)):
    pet = db.scalar(select(Pet).where(Pet.medical_secret_token == token))
    if not pet:
        raise HTTPException(404, "Medical card not found")
    age_years = None
    if pet.birth_date:
        today = date.today()
        age_years = today.year - pet.birth_date.year - ((today.month, today.day) < (pet.birth_date.month, pet.birth_date.day))
    vaccinations = [
        {"title": event.title, "date": event.starts_at, "status": event.status}
        for event in pet.events if event.event_type in {"vaccine", "vaccination"}
    ]
    return {
        "id": pet.id, "name": pet.name, "species": pet.species, "breed": pet.breed,
        "birth_date": pet.birth_date, "sex": pet.sex, "weight_kg": pet.weight_kg, "height_cm": pet.height_cm,
        "photo_url": pet.photo_url, "age_years": age_years, "vaccinations": vaccinations,
    }

@router.get("/{pet_id}", response_model=PetResponse)
def get_pet(pet_id: int, db: Session = Depends(get_db)):
    return _get(db, pet_id)

@router.patch("/{pet_id}", response_model=PetResponse)
def update_pet(pet_id: int, payload: PetUpdate, db: Session = Depends(get_db)):
    pet = _get(db, pet_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(pet, key, value)
    db.commit(); db.refresh(pet)
    return pet

@router.delete("/{pet_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pet(pet_id: int, db: Session = Depends(get_db)):
    pet = _get(db, pet_id)
    db.delete(pet); db.commit()

@router.post("/{pet_id}/photo", response_model=PetResponse)
async def upload_photo(pet_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    pet = _get(db, pet_id)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(400, "Only jpg, png and webp images are supported")
    directory = Path(get_settings().upload_dir); directory.mkdir(parents=True, exist_ok=True)
    filename = f"{token_urlsafe(16)}{suffix}"
    (directory / filename).write_bytes(await file.read())
    pet.photo_url = f"/uploads/{filename}"
    db.commit(); db.refresh(pet)
    return pet

@router.post("/{pet_id}/medical-token", response_model=PetResponse)
def renew_medical_token(pet_id: int, db: Session = Depends(get_db)):
    pet = _get(db, pet_id)
    pet.medical_secret_token = token_urlsafe(32)
    db.commit(); db.refresh(pet)
    return pet
