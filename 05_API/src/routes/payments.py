from fastapi import APIRouter, Depends, HTTPException, Header, Response, status
from sqlalchemy.orm import Session

try:
    from ..database import get_db
    from ..models.schemas import ChargeRequest, PaymentResponse
    from ..services.payment_service import PaymentService
    from ..events.outbox_relay import outbox_relay
except (ImportError, ValueError):
    from database import get_db
    from models.schemas import ChargeRequest, PaymentResponse
    from services.payment_service import PaymentService
    from events.outbox_relay import outbox_relay

router = APIRouter(prefix="/payments", tags=["Payment Processing"])

@router.post("/charges", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
def process_payment_charge(
    req: ChargeRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db)
):
    svc = PaymentService(db)
    result = svc.process_charge(
        reservation_id=req.reservation_id,
        payment_token=req.payment_token,
        amount=req.amount,
        currency=req.currency,
        idempotency_key=idempotency_key
    )

    pay = result["payment"]
    outbox_relay.process_pending_events()

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "PAYMENT_DECLINED",
                "message": result.get("message", "Payment authorization declined by provider."),
                "payment_id": pay.payment_id
            }
        )

    if result["duplicate"]:
        response.status_code = status.HTTP_200_OK

    return PaymentResponse(
        payment_id=pay.payment_id,
        reservation_id=pay.reservation_id,
        status=pay.status,
        amount=float(pay.amount),
        currency=pay.currency,
        provider_transaction_id=pay.provider_transaction_id,
        created_at=pay.created_at.isoformat() if hasattr(pay.created_at, "isoformat") else str(pay.created_at)
    )
