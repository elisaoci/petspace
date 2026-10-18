from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class PetBase(BaseModel):
    name: str
    species: str = "dog"
    breed: str | None = None
    birth_date: date | None = None
    sex: str | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    owner_notes: str | None = None
    allergies: str | None = None
    chronic_conditions: str | None = None

class PetCreate(PetBase): pass
class PetUpdate(BaseModel):
    name: str | None = None
    species: str | None = None
    breed: str | None = None
    birth_date: date | None = None
    sex: str | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    owner_notes: str | None = None
    allergies: str | None = None
    chronic_conditions: str | None = None

class PetResponse(PetBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    photo_url: str | None
    medical_secret_token: str
    created_at: datetime

class PublicVaccination(BaseModel):
    title: str
    date: datetime
    status: str

class PublicMedicalCard(BaseModel):
    id: int
    name: str
    species: str
    breed: str | None
    birth_date: date | None
    sex: str | None
    weight_kg: float | None
    height_cm: float | None
    photo_url: str | None
    allergies: str | None = None
    chronic_conditions: str | None = None
    age_years: int | None = None
    vaccinations: list[PublicVaccination] = Field(default_factory=list)
