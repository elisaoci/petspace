from datetime import datetime
from pydantic import BaseModel, ConfigDict

class EventCreate(BaseModel):
    pet_id: int
    title: str
    description: str | None = None
    event_type: str = "other"
    starts_at: datetime
    ends_at: datetime | None = None
    status: str = "planned"

class EventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    event_type: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    status: str | None = None

class EventResponse(EventCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    computed_status: str
