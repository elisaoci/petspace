from pydantic import BaseModel, Field


class DemoPaymentRequest(BaseModel):
    owner_id: str
    plan: str = "premium"
    amount: int = Field(gt=0)
    currency: str = "RUB"

class DemoPaymentResponse(BaseModel):
    payment_id: str
    status: str
    plan: str
    amount: int
    currency: str
