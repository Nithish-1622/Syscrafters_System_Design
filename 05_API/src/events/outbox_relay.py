import json
import time
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session

try:
    from ..models.db_models import TransactionalOutbox
    from ..services.order_service import OrderService
    from ..database import SessionLocal
except (ImportError, ValueError):
    from models.db_models import TransactionalOutbox
    from services.order_service import OrderService
    from database import SessionLocal

logger = logging.getLogger("outbox_relay")

class OutboxRelayService:
    def __init__(self):
        self.is_running = True
        self.order_service_healthy = True

    def set_order_service_health(self, is_healthy: bool):
        self.order_service_healthy = is_healthy

    def process_pending_events(self) -> int:
        db = SessionLocal()
        try:
            pending = db.query(TransactionalOutbox).filter(
                TransactionalOutbox.status == "PENDING"
            ).order_by(TransactionalOutbox.created_at.asc()).limit(50).all()

            if not pending:
                return 0

            processed_count = 0
            order_svc = OrderService(db)

            for entry in pending:
                if entry.event_type == "PaymentSucceeded":
                    if not self.order_service_healthy:
                        logger.warning(f"Order Service offline. Event {entry.event_id} safely buffered in outbox.")
                        continue

                    payload = json.loads(entry.payload)
                    event_data = payload.get("data", {})
                    
                    res = order_svc.create_order_from_payment_event(event_data)
                    if res["success"]:
                        entry.status = "PUBLISHED"
                        entry.published_at = datetime.now(timezone.utc)
                        processed_count += 1
                    else:
                        entry.retry_count += 1
                        if entry.retry_count > 3:
                            entry.status = "FAILED"

            db.commit()
            return processed_count
        finally:
            db.close()

outbox_relay = OutboxRelayService()
