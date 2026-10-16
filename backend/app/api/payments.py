from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.schemas.payments import DemoPaymentRequest, DemoPaymentResponse
from app.services.payments import process_demo_payment

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/demo", response_model=DemoPaymentResponse)
def demo_payment(payload: DemoPaymentRequest, user: CurrentUser):
    """Демо-оплата: карта не обрабатывается и не сохраняется. Требует авторизации."""
    return process_demo_payment(payload)
