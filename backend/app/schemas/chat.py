from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: str = "default"
    pet_id: int | None = None

class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: str
