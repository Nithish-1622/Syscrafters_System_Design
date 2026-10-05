import uuid
import json
import random
from datetime import datetime, timezone
from sqlalchemy.orm import Session

try:
    from ..models.db_models import Payment, InventoryReservation, TransactionalOutbox
    from .inventory_service import InventoryService
except (ImportError, ValueError):
    from models.db_models import Payment, InventoryReservation, TransactionalOutbox
    from services.inventory_service import InventoryService

class PaymentService:
    def __init__(self, db: Session):
        self.db = db
        self.inventory_service = InventoryService(db)

    def process_charge(self, reservation_id: str, payment_token: str, amount: float, currency: str, idempotency_key: str, force_failure: bool = False) -> dict:
        existing_pay = self.db.query(Payment).filter(Payment.idempotency_key == idempotency_key).first()
        if existing_pay:
            return {
                "success": existing_pay.status == "SUCCEEDED",
                "duplicate": True,
                "payment": existing_pay
            }

        reservation = self.db.query(InventoryReservation).filter(
            InventoryReservation.reservation_id == reservation_id
        ).first()

        if not reservation:
            return {"success": False, "error": "RESERVATION_NOT_FOUND", "message": "Reservation does not exist."}

        if reservation.status != "RESERVED" and reservation.status != "PAYMENT_PENDING":
            return {"success": False, "error": "RESERVATION_INVALID_STATE", "message": f"Reservation is {reservation.status}"}

        reservation.status = "PAYMENT_PENDING"
        self.db.commit()

        is_success = not force_failure
        if not force_failure and payment_token == "tok_force_decline":
            is_success = False

        payment_id = str(uuid.uuid4())
        provider_tx = f"ch_stripe_{uuid.uuid4().hex[:12]}" if is_success else None
        status = "SUCCEEDED" if is_success else "FAILED"
        failure_reason = None if is_success else "CARD_DECLINED_INSUFFICIENT_FUNDS"

        payment = Payment(
            payment_id=payment_id,
            reservation_id=reservation_id,
            customer_id=reservation.customer_id,
            amount=amount,
            currency=currency,
            provider="STRIPE",
            provider_transaction_id=provider_tx,
            idempotency_key=idempotency_key,
            status=status,
            failure_reason=failure_reason
        )
        self.db.add(payment)

        if is_success:
            event_payload = {
                "specversion": "1.0",
                "id": str(uuid.uuid4()),
                "source": "/services/payment-service",
                "type": "io.salestorm.payment.succeeded",
                "time": datetime.now(timezone.utc).isoformat(),
                "data": {
                    "payment_id": payment_id,
                    "reservation_id": reservation_id,
                    "customer_id": reservation.customer_id,
                    "product_id": reservation.product_id,
                    "quantity": reservation.quantity,
                    "amount": amount,
                    "currency": currency,
                    "provider_transaction_id": provider_tx
                }
            }
            outbox_entry = TransactionalOutbox(
                aggregate_type="PAYMENT",
                aggregate_id=payment_id,
                event_type="PaymentSucceeded",
                payload=json.dumps(event_payload),
                correlation_id=str(uuid.uuid4()),
                status="PENDING"
            )
            self.db.add(outbox_entry)
            self.db.commit()
            self.db.refresh(payment)

            return {
                "success": True,
                "duplicate": False,
                "payment": payment
            }
        else:
            self.db.commit()
            self.db.refresh(payment)
            self.inventory_service.release(reservation_id, reason="PAYMENT_FAILED")

            return {
                "success": False,
                "duplicate": False,
                "error": "PAYMENT_DECLINED",
                "message": failure_reason,
                "payment": payment
            }
