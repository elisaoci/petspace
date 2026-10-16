from fastapi import APIRouter

from app.schemas.payments import DemoPaymentRequest, DemoPaymentResponse
from app.services.payments import process_demo_payment

router = APIRouter(prefix="/payments", tags=["payments"])

@router.post("/demo", response_model=DemoPaymentResponse)
def demo_payment(payload: DemoPaymentRequest):
    return process_demo_payment(payload)
