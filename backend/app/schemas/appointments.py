"""Схемы заявки на приём."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AppointmentCreate(BaseModel):
    clinic_name: str = Field(min_length=1, max_length=200)
    slot_start: datetime
    comment: str | None = Field(default=None, max_length=2000)


class AppointmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pet_id: int
    clinic_name: str
    slot_start: datetime
    comment: str | None
    status: str
    created_at: datetime
    updated_at: datetime
