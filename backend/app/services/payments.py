from secrets import token_urlsafe

from app.schemas.payments import DemoPaymentRequest, DemoPaymentResponse


def process_demo_payment(payload: DemoPaymentRequest) -> DemoPaymentResponse:
    """Return a deterministic demo success without ever handling card data."""
    return DemoPaymentResponse(
        payment_id=f"demo_{token_urlsafe(12)}",
        status="succeeded",
        plan=payload.plan,
        amount=payload.amount,
        currency=payload.currency,
    )
